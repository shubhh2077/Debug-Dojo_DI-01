"""Per-test execution with a fail-closed local development fallback.

Production execution should use Docker. The local path is retained for
development and refuses to execute on platforms where required OS limits are
not enforceable.
"""

from __future__ import annotations

import builtins
import json
import multiprocessing as mp
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows
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


def platform_limits() -> dict[str, str]:
    """Report actual enforcement, not merely intended configuration."""
    supported = resource is not None
    return {
        "wall timeout": "enforced",
        "CPU": "enforced" if supported else "unavailable",
        "memory": "enforced" if supported else "unavailable",
        "file size": "enforced" if supported else "unavailable",
        "process count": "enforced" if supported else "unavailable",
        "open files": "enforced" if supported else "unavailable",
        "network": "blocked (import policy; Docker: network none)",
        "filesystem": "restricted child cwd/open policy; Docker: read-only + tmpfs",
    }


def format_platform_audit() -> str:
    rows = ["| Limit | Status |", "|---|---|"]
    rows.extend(f"| {name} | {status} |" for name, status in platform_limits().items())
    return "\n".join(rows)


def sweep_stale_sandboxes() -> list[str]:
    """Remove only named stale directories in the OS temp directory."""
    removed: list[str] = []
    roots = [Path(tempfile.gettempdir()), Path(__file__).resolve().parents[1]]
    for root in roots:
        for path in root.glob(f"{SANDBOX_PREFIX}*"):
            if path.is_dir():
                _remove_tree(path)
                if not path.exists():
                    removed.append(str(path))
    return removed


def _remove_tree(path: Path) -> None:
    last_error: OSError | None = None
    for _ in range(5):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    print(f"warning: could not remove sandbox {path}: {last_error}", file=sys.stderr)


def _apply_limits() -> None:
    if resource is None:
        raise RuntimeError("required OS resource limits unavailable; use Docker")
    for name, limit in (
        ("RLIMIT_CPU", (2, 2)),
        ("RLIMIT_AS", (128 * 1024 * 1024, 128 * 1024 * 1024)),
        ("RLIMIT_FSIZE", (1024 * 1024, 1024 * 1024)),
        ("RLIMIT_NPROC", (32, 32)),
        ("RLIMIT_NOFILE", (64, 64)),
    ):
        constant = getattr(resource, name, None)
        if constant is None:
            raise RuntimeError(f"required OS limit unavailable: {name}")
        resource.setrlimit(constant, limit)


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
    if len(encoded) > MAX_MESSAGE:
        encoded = json.dumps({"status": "error", "error": "output limit exceeded"}).encode()
    conn.send_bytes(encoded)


def _child(code: str, function_name: str, args: list[Any], sandbox: str, conn: Any,
           enforce_limits: bool) -> None:
    try:
        os.environ.clear()
        os.chdir(sandbox)
        if hasattr(os, "setsid"):
            os.setsid()
        if enforce_limits:
            _apply_limits()
        safe_builtins = dict(vars(builtins))
        safe_builtins.update({
            "__import__": _safe_import,
            "open": lambda *a, **k: (_ for _ in ()).throw(PermissionError("file access blocked")),
            "breakpoint": lambda *a, **k: None,
        })
        namespace: dict[str, Any] = {"__builtins__": safe_builtins, "__name__": "__learner__"}
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
        encoded_value = json.dumps(value, allow_nan=False, separators=(", ", ":"))
        if len(encoded_value.encode()) > MAX_OUTPUT:
            raise MemoryError("output limit exceeded")
        _send(conn, {"status": "ok", "value": json.loads(encoded_value), "stdout": stdout.text})
    except BaseException as exc:
        try:
            if isinstance(exc, MemoryError):
                reason = "memory limit exceeded"
            elif isinstance(exc, OSError) and getattr(exc, "errno", None) == 27:
                reason = "file size limit exceeded"
            elif isinstance(exc, PermissionError):
                reason = f"filesystem limit: {str(exc)[:160]}"
            else:
                reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            _send(conn, {"status": "error", "error": reason})
        except (BrokenPipeError, OSError):
            pass
    finally:
        conn.close()


def _terminate(process: mp.Process) -> None:
    if process.is_alive():
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        process.terminate()
        process.join(1)
    if process.is_alive():
        process.kill()
        process.join()


def _decode(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_MESSAGE:
        raise ValueError("result channel limit exceeded")
    message = json.loads(raw.decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("invalid result message")
    return message


def _run_local(code: str, function_name: str, args: list[Any], expected: Any,
               timeout: float, enforce_limits: bool) -> Execution:
    if enforce_limits and resource is None:
        return Execution("runtime_error", error="required OS limits unavailable; use Docker")
    sandbox = tempfile.mkdtemp(prefix=SANDBOX_PREFIX, dir=tempfile.gettempdir())
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(code, function_name, args, sandbox, child, enforce_limits))
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
            message = _decode(raw)
        except (EOFError, OSError, ValueError, json.JSONDecodeError):
            detail = "resource limit exceeded" if process.exitcode not in (0, None) else "invalid or missing child result"
            return Execution("runtime_error", error=detail)
        if message.get("status") != "ok":
            return Execution("runtime_error", error=str(message.get("error", "child failed")))
        value = message.get("value")
        stdout = str(message.get("stdout", ""))[:MAX_OUTPUT]
        return Execution("passed" if value == expected else "wrong_output", value=value, stdout=stdout)
    except BaseException as exc:
        return Execution("runtime_error", error=f"runner failure: {type(exc).__name__}")
    finally:
        parent.close()
        if process.is_alive():
            _terminate(process)
        if started:
            process.join()
        _remove_tree(Path(sandbox))


def run_test(code: str, function_name: str, args: list[Any], expected: Any,
             timeout: float = 2.0, mode: str = "local") -> Execution:
    """Run one test. `local` is development-only; `docker` is production mode."""
    if mode == "docker":
        return _run_docker(code, function_name, args, expected, timeout)
    if mode == "local-dev":
        return _run_local(code, function_name, args, expected, timeout, enforce_limits=False)
    if mode != "local":
        return Execution("runtime_error", error="unknown runner mode")
    return _run_local(code, function_name, args, expected, timeout, enforce_limits=True)


def _run_docker(code: str, function_name: str, args: list[Any], expected: Any,
                timeout: float) -> Execution:
    payload = json.dumps({"code": code, "function_name": function_name, "args": args}).encode()
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--memory", "128m",
        "--pids-limit", "64", "--cpus", "0.5", "--cap-drop", "ALL",
        "debug-dojo:latest",
    ]
    try:
        completed = subprocess.run(command, input=payload, capture_output=True, timeout=timeout + 2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Execution("runtime_error", error=f"Docker runner unavailable: {type(exc).__name__}")
    if completed.returncode != 0:
        return Execution("runtime_error", error="container limit or process failure")
    try:
        message = _decode(completed.stdout)
        if message.get("status") != "ok":
            return Execution("runtime_error", error=str(message.get("error", "child failed")))
        value = message.get("value")
        return Execution("passed" if value == expected else "wrong_output", value=value,
                         stdout=str(message.get("stdout", ""))[:MAX_OUTPUT])
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return Execution("runtime_error", error="invalid container result")


def run_challenge(code: str, challenge: dict[str, Any], mode: str = "local") -> tuple[list[Execution], list[Execution]]:
    visible = [run_test(code, challenge["function_name"], t["args"], t["expected"], mode=mode)
               for t in challenge["visible_tests"]]
    hidden = [run_test(code, challenge["function_name"], t["args"], t["expected"], mode=mode)
              for t in challenge["hidden_tests"]]
    return visible, hidden
