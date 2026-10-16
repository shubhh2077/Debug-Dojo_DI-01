"""Fail-closed per-test learner execution on Linux."""

from __future__ import annotations

import builtins
import copy
import json
import multiprocessing as mp
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - native Windows
    resource = None  # type: ignore[assignment]

MAX_MESSAGE = 128 * 1024
MAX_OUTPUT = 64 * 1024
SANDBOX_PREFIX = "debug-dojo-"


@dataclass
class Execution:
    outcome: str
    value: Any = None
    error: str = ""
    stdout: str = ""
    returned_none: bool = False
    printed_output: bool = False
    mutated_input: bool = False
    error_type: str = ""


def require_resource_limits() -> None:
    """Refuse startup unless this Linux process can apply every required limit."""
    if resource is None:
        raise RuntimeError("Run inside WSL2 or Docker (see README)")
    required = ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_NPROC", "RLIMIT_NOFILE")
    if any(getattr(resource, name, None) is None for name in required):
        raise RuntimeError("Run inside WSL2 or Docker (see README)")


def platform_limits() -> dict[str, str]:
    supported = resource is not None
    return {
        "wall timeout": "enforced",
        "CPU": "enforced" if supported else "unavailable",
        "memory": "enforced" if supported else "unavailable",
        "file size": "enforced" if supported else "unavailable",
        "process count": "enforced" if supported else "unavailable",
        "open files": "enforced" if supported else "unavailable",
        "network": "blocked (import policy)",
        "filesystem": "restricted child cwd/open policy",
    }


def format_platform_audit() -> str:
    rows = ["| Limit | Status |", "|---|---|"]
    rows.extend(f"| {name} | {status} |" for name, status in platform_limits().items())
    return "\n".join(rows)


def _remove_tree(path: Path) -> None:
    for _ in range(5):
        try:
            import shutil
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            time.sleep(0.05)
    print(f"warning: could not remove sandbox {path}: {exc}", file=sys.stderr)


def sweep_stale_sandboxes() -> None:
    for root in (Path(tempfile.gettempdir()), Path(__file__).resolve().parents[1]):
        for path in root.glob(f"{SANDBOX_PREFIX}*"):
            if path.is_dir():
                _remove_tree(path)


def _apply_limits() -> None:
    require_resource_limits()
    for name, limit in (
        ("RLIMIT_CPU", (2, 2)),
        ("RLIMIT_AS", (128 * 1024 * 1024, 128 * 1024 * 1024)),
        ("RLIMIT_FSIZE", (1024 * 1024, 1024 * 1024)),
        ("RLIMIT_NPROC", (32, 32)),
        ("RLIMIT_NOFILE", (64, 64)),
    ):
        resource.setrlimit(getattr(resource, name), limit)


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    allowed = {"math", "statistics", "itertools", "functools", "operator"}
    if name.split(".", 1)[0] not in allowed:
        raise ImportError(f"import blocked: {name}")
    return builtins.__import__(name, *args, **kwargs)


class _CappedWriter:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0
        self.exceeded = False

    def write(self, text: str) -> int:
        remaining = max(0, MAX_OUTPUT - self.size)
        self.parts.append(text[:remaining])
        self.size += min(len(text), remaining)
        self.exceeded = self.exceeded or len(text) > remaining
        return len(text)

    def flush(self) -> None:
        pass

    @property
    def text(self) -> str:
        return "".join(self.parts)


def _send(conn: Any, message: dict[str, Any]) -> None:
    encoded = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
    conn.send_bytes(encoded[:MAX_MESSAGE])


def _child(code: str, function_name: str, args: list[Any], sandbox: str, conn: Any) -> None:
    try:
        os.environ.clear()
        os.chdir(sandbox)
        os.setsid()
        _apply_limits()
        safe_builtins = dict(vars(builtins))
        safe_builtins.update({
            "__import__": _safe_import,
            "open": lambda *a, **k: (_ for _ in ()).throw(PermissionError("file access blocked")),
            "breakpoint": lambda *a, **k: None,
        })
        namespace: dict[str, Any] = {"__builtins__": safe_builtins, "__name__": "__learner__"}
        before = copy.deepcopy(args)
        stdout = _CappedWriter()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = stdout
        try:
            exec(compile(code, "<learner>", "exec"), namespace, namespace)
            function = namespace.get(function_name)
            if not callable(function):
                raise NameError(f"missing function: {function_name}")
            value = function(*args)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
        if stdout.exceeded:
            raise RuntimeError("output limit exceeded")
        encoded_value = json.dumps(value, allow_nan=False, separators=(",", ":"))
        if len(encoded_value.encode()) > MAX_OUTPUT:
            raise MemoryError("output limit exceeded")
        _send(conn, {
            "status": "ok",
            "value": json.loads(encoded_value),
            "stdout": stdout.text,
            "returned_none": value is None,
            "printed_output": bool(stdout.text),
            "mutated_input": args != before,
        })
    except BaseException as exc:
        try:
            _send(conn, {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                         "error_type": type(exc).__name__})
        except (BrokenPipeError, OSError):
            pass
    finally:
        conn.close()


def _terminate(process: mp.Process) -> None:
    if process.is_alive():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            process.terminate()
        process.join(1)
    if process.is_alive():
        process.kill()
        process.join()


def run_test(code: str, function_name: str, args: list[Any], expected: Any,
             timeout: float = 1.5) -> Execution:
    """Run one test; expected data remains in this parent process."""
    try:
        require_resource_limits()
        sandbox = tempfile.mkdtemp(prefix=SANDBOX_PREFIX, dir=tempfile.gettempdir())
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_child, args=(code, function_name, args, sandbox, child))
        started = False
        try:
            process.start()
            started = True
            child.close()
            process.join(timeout)
            if process.is_alive():
                _terminate(process)
                return Execution("timeout")
            try:
                raw = parent.recv_bytes(MAX_MESSAGE)
                message = json.loads(raw.decode("utf-8"))
                if not isinstance(message, dict):
                    raise ValueError("invalid child result")
            except (EOFError, OSError, ValueError, json.JSONDecodeError):
                return Execution("runtime_error", error="invalid or missing child result")
            if message.get("status") != "ok":
                return Execution("runtime_error", error=str(message.get("error", "child failed")),
                                 error_type=str(message.get("error_type", "")))
            value = message.get("value")
            metadata = {
                key: bool(message.get(key, False))
                for key in ("returned_none", "printed_output", "mutated_input")
            }
            return Execution("passed" if value == expected else "wrong_output",
                             value=value, stdout=str(message.get("stdout", ""))[:MAX_OUTPUT],
                             **metadata)
        except BaseException as exc:
            return Execution("runtime_error", error=f"runner failure: {type(exc).__name__}")
        finally:
            parent.close()
            if started and process.is_alive():
                _terminate(process)
            if started:
                process.join()
            _remove_tree(Path(sandbox))
    except BaseException as exc:
        return Execution("runtime_error", error=f"runner failure: {type(exc).__name__}")


def run_challenge(code: str, challenge: dict[str, Any]) -> tuple[list[Execution], list[Execution]]:
    visible = [run_test(code, challenge["function_name"], t["args"], t["expected"])
               for t in challenge["visible_tests"]]
    hidden = [run_test(code, challenge["function_name"], t["args"], t["expected"])
              for t in challenge["hidden_tests"]]
    return visible, hidden
