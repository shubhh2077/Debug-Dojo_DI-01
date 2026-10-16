from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from dojo.runner import (
    format_platform_audit,
    platform_limits,
    run_test,
    sweep_stale_sandboxes,
)

ROOT = Path(__file__).parents[1]


def test_platform_audit_is_actual():
    table = format_platform_audit()
    assert "| wall timeout | enforced |" in table
    if sys.platform == "win32":
        assert platform_limits()["memory"] == "unavailable"
        assert run_test("def f(): return 1", "f", [], 1).outcome == "runtime_error"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX resource limits are unavailable on Windows")
def test_resource_limits_are_available_on_posix():
    assert platform_limits()["memory"] == "enforced"


def test_pipe_is_bounded_json_and_never_executes_parent_payload():
    result = run_test(
        "class Payload:\n"
        "    def __reduce__(self):\n"
        "        return (print, ('PARENT_EXECUTED',))\n"
        "def f(): return Payload()",
        "f", [], None,
    )
    assert result.outcome == "runtime_error"
    assert "PARENT_EXECUTED" not in result.stdout


@pytest.mark.parametrize("code", [
    "def f(): return open('../challenges/last-k-total.json').read()",
    "def f(): return open('../../dojo/runner.py').read()",
    f"def f(): return open({str(ROOT / 'challenges' / 'last-k-total.json')!r}).read()",
    f"def f(): return open({str(ROOT / 'dojo' / 'runner.py')!r}).read()",
])
def test_child_cannot_read_repo_or_challenges(code):
    result = run_test(code, "f", [], None)
    assert result.outcome == "runtime_error"
    assert "id\": \"last-k-total\"" not in result.error
    assert "def run_test" not in result.error


def test_sandbox_cleanup_after_timeout_and_file_attempt():
    sweep_stale_sandboxes()
    for code in [
        "def f():\n    while True: pass",
        "def f():\n    open('x', 'w').write('x')",
        "def f(): return 1",
    ]:
        run_test(code, "f", [], 1, timeout=0.2)
    assert not list(Path(os.environ.get("TEMP", "/tmp")).glob("debug-dojo-*"))
    assert not list(ROOT.glob("debug-dojo-*"))


@pytest.mark.parametrize("code", [
    "def f(): print('x' * (10**8))",
    "def f(): return [0] * (10**8)",
    "def f():\n    def recurse(): recurse()\n    recurse()",
])
def test_visible_limit_failures_name_limit(code):
    result = run_test(code, "f", [], None, timeout=0.5)
    assert result.outcome in {"runtime_error", "timeout"}
    if result.outcome == "runtime_error":
        assert any(word in result.error.lower() for word in ("output", "memory", "recursion", "limit"))


@pytest.mark.parametrize("code", [
    "def f():\n    import threading\n    threading.Thread(target=lambda: 1/0).start()\n    return 0",
    "def f():\n    import os\n    os.fork()\n    return 0",
    "def f():\n    import os\n    os.remove('../dojo/runner.py')\n    return 0",
    "def f(): return __import__('os').environ",
    "def f():\n    try: raise SystemExit(0)\n    except BaseException: print('passed')\n    return None",
    "def f():\n    globals()['f'] = lambda: 999\n    return 999",
])
def test_extra_hostile_programs_are_not_passed_and_recovery_works(code):
    result = run_test(code, "f", [], 0, timeout=0.5)
    assert result.outcome != "passed"
    normal = run_test("def f(): return 1", "f", [], 1)
    assert normal.outcome == "passed"
