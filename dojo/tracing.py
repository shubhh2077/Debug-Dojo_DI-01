"""Restricted educational tracing for one explicitly selected public case.

This module is intentionally separate from judging. It runs learner code in a
fresh child process, applies the existing resource limits, and returns only
bounded JSON-safe snapshots.
"""
from __future__ import annotations

import builtins
import json
import multiprocessing as mp
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .runner import (
    MAX_MESSAGE,
    _CappedWriter,
    _apply_limits,
    _remove_tree,
    _safe_import,
    _terminate,
)

MAX_STEPS = 200
MAX_VALUE_CHARS = 240
MAX_OUTPUT = 64 * 1024
TRACE_TIMEOUT = 1.5


class _TraceLimit(Exception):
    """Raised inside the child when the educational event budget is reached."""


def _safe_value(value: Any, depth: int = 0) -> dict[str, Any]:
    """Return a bounded representation without calling learner repr methods."""
    value_type = type(value).__name__
    if depth > 2:
        return {"type": value_type, "value": "<nested value omitted>"}
    if value is None or isinstance(value, (bool, int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple)):
        return {
            "type": value_type,
            "value": [_safe_value(item, depth + 1) for item in list(value)[:12]],
            "length": len(value),
            "truncated": len(value) > 12,
        }
    elif isinstance(value, dict):
        items: dict[str, Any] = {}
        for key in list(value)[:12]:
            if isinstance(key, (str, int, float, bool)):
                items[str(key)[:60]] = _safe_value(value[key], depth + 1)
        return {
            "type": "dict",
            "value": items,
            "length": len(value),
            "truncated": len(value) > 12,
        }
    else:
        return {"type": value_type, "value": "<value unavailable>"}
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS] + "…"
    return {"type": value_type, "value": text}


def _snapshot(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        if name.startswith("__"):
            continue
        try:
            result[name] = _safe_value(value)
        except BaseException:
            result[name] = {"type": "unavailable", "value": "<value unavailable>"}
    return result


def _changed(previous: dict[str, dict[str, Any]] | None,
            current: dict[str, dict[str, Any]]) -> list[str]:
    if previous is None:
        return []
    return sorted(
        name for name in set(previous) | set(current)
        if previous.get(name) != current.get(name)
    )


def _send(conn: Any, message: dict[str, Any]) -> None:
    encoded = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_MESSAGE:
        encoded = json.dumps({
            "status": "truncated",
            "events": [],
            "return_value": None,
            "truncated": True,
        }).encode()
    conn.send_bytes(encoded)


def _trace_child(code: str, function_name: str, args: list[Any],
                 sandbox: str, conn: Any) -> None:
    events: list[dict[str, Any]] = []
    previous: dict[str, dict[str, Any]] | None = None
    steps = 0
    stdout = _CappedWriter()
    try:
        os.environ.clear()
        os.chdir(sandbox)
        if hasattr(os, "setsid"):
            os.setsid()
        _apply_limits()
        safe_builtins = dict(vars(builtins))
        safe_builtins.update({
            "__import__": _safe_import,
            "open": lambda *a, **k: (_ for _ in ()).throw(
                PermissionError("file access blocked")
            ),
            "breakpoint": lambda *a, **k: None,
        })
        namespace: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": "__learner__",
        }
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = stdout
        source_name = "<learner>"

        def trace(frame: Any, event: str, arg: Any) -> Any:
            nonlocal previous, steps
            if frame.f_code.co_filename != source_name:
                return trace
            if event not in {"line", "call", "return"}:
                return trace
            if steps >= MAX_STEPS:
                raise _TraceLimit
            current = _snapshot(frame.f_locals)
            steps += 1
            events.append({
                "step": steps,
                "line": frame.f_lineno,
                "event": event,
                "function": frame.f_code.co_name,
                "locals": current,
                "changes": _changed(previous, current),
            })
            previous = current
            return trace

        sys.settrace(trace)
        try:
            exec(compile(code, source_name, "exec"), namespace, namespace)
            function = namespace.get(function_name)
            if not callable(function):
                raise NameError("missing function")
            value = function(*args)
        finally:
            sys.settrace(None)
            sys.stdout, sys.stderr = old_stdout, old_stderr
        if stdout.exceeded:
            raise RuntimeError("output limit exceeded")
        _send(conn, {
            "status": "completed",
            "events": events,
            "return_value": _safe_value(value),
            "truncated": False,
        })
    except _TraceLimit:
        _send(conn, {
            "status": "truncated",
            "events": events,
            "return_value": None,
            "truncated": True,
        })
    except BaseException as exc:
        try:
            _send(conn, {
                "status": "runtime_error",
                "events": events,
                "return_value": None,
                "error": "execution failed",
                "truncated": False,
            })
        except (BrokenPipeError, OSError):
            pass
    finally:
        conn.close()


def trace_public_case(code: str, function_name: str, args: list[Any],
                      timeout: float = TRACE_TIMEOUT) -> dict[str, Any]:
    """Trace one already-selected public case in a restricted child process."""
    if len(code.encode("utf-8")) > 20 * 1024:
        return {
            "status": "runtime_error", "events": [], "return_value": None,
            "error": "code limit exceeded", "truncated": False,
        }
    sandbox = tempfile.mkdtemp(prefix="debug-dojo-", dir=tempfile.gettempdir())
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_trace_child,
        args=(code, function_name, args, sandbox, child),
    )
    started = False
    try:
        process.start()
        started = True
        child.close()
        process.join(timeout)
        if process.is_alive():
            _terminate(process)
            return {
                "status": "timeout", "events": [], "return_value": None,
                "error": "execution timed out", "truncated": False,
            }
        try:
            raw = parent.recv_bytes(MAX_MESSAGE)
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("invalid trace result")
            return result
        except (EOFError, OSError, ValueError, json.JSONDecodeError):
            return {
                "status": "runtime_error", "events": [], "return_value": None,
                "error": "invalid trace result", "truncated": False,
            }
    except BaseException:
        return {
            "status": "runtime_error", "events": [], "return_value": None,
            "error": "trace runner failure", "truncated": False,
        }
    finally:
        parent.close()
        if started and process.is_alive():
            _terminate(process)
        if started:
            process.join()
        _remove_tree(Path(sandbox))
