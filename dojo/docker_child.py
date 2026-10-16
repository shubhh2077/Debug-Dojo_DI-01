"""Minimal child used inside the Docker sandbox; it never loads challenge files."""

from __future__ import annotations

import builtins
import io
import json
import os
import sys


def main() -> None:
    request = json.loads(sys.stdin.buffer.read(128 * 1024))
    os.environ.clear()
    os.chdir("/tmp")
    allowed = {"math", "statistics", "itertools", "functools", "operator"}
    original_import = builtins.__import__
    builtins.__import__ = lambda name, *a, **k: (
        original_import(name, *a, **k) if name.split(".", 1)[0] in allowed
        else (_ for _ in ()).throw(ImportError("import blocked"))
    )
    namespace = {"__builtins__": dict(vars(builtins)), "__name__": "__learner__"}
    namespace["__builtins__"]["open"] = lambda *a, **k: (_ for _ in ()).throw(PermissionError("file access blocked"))
    output = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = sys.stderr = output
        exec(compile(request["code"], "<learner>", "exec"), namespace, namespace)
        function = namespace.get(request["function_name"])
        if not callable(function):
            raise NameError("missing function")
        value = function(*request["args"])
        if output.tell() > 64 * 1024:
            raise MemoryError("output limit exceeded")
        result = {"status": "ok", "value": value, "stdout": output.getvalue()[:64 * 1024]}
    except BaseException as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
