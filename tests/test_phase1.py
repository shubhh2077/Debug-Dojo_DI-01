from __future__ import annotations

import json
from pathlib import Path

import pytest

from dojo.runner import run_test
from dojo.tests_loader import load_challenges

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def challenges():
    return load_challenges(ROOT / "challenges")


@pytest.mark.parametrize("challenge_id", [
    "last-k-total", "count-passes", "first-n-squares", "middle-three",
])
def test_required_challenge_has_valid_shape(challenges, challenge_id):
    challenge = challenges[challenge_id]
    assert len(challenge["visible_tests"]) >= 3
    assert len(challenge["hidden_tests"]) >= 5


@pytest.mark.parametrize(("challenge_id", "code"), [
    ("last-k-total", "def last_k_total(marks, k): return sum(marks[-k:]) if k else 0"),
    ("count-passes", "def count_passes(marks): return sum(mark >= 40 for mark in marks)"),
    ("first-n-squares", "def first_n_squares(n): return [i * i for i in range(1, n + 1)]"),
    ("middle-three", "def middle_three(items): return items if len(items) < 3 else items[len(items)//2-1:len(items)//2+2]"),
])
def test_passing_program(challenges, challenge_id, code):
    challenge = challenges[challenge_id]
    for test in challenge["visible_tests"]:
        result = run_test(code, challenge["function_name"], test["args"], test["expected"])
        assert result.outcome == "passed"


@pytest.mark.parametrize(("challenge_id", "code", "test_index"), [
    ("last-k-total", "def last_k_total(marks, k): return sum(marks[:k])", 0),
    ("count-passes", "def count_passes(marks): return sum(mark > 40 for mark in marks)", 0),
    ("first-n-squares", "def first_n_squares(n): return [i*i for i in range(n)]", 1),
    ("middle-three", "def middle_three(items): return items[:3]", 0),
])
def test_wrong_output_program(challenges, challenge_id, code, test_index):
    challenge = challenges[challenge_id]
    result = run_test(code, challenge["function_name"],
                      challenge["visible_tests"][test_index]["args"],
                      challenge["visible_tests"][test_index]["expected"])
    assert result.outcome == "wrong_output"


@pytest.mark.parametrize("challenge_id", [
    "last-k-total", "count-passes", "first-n-squares", "middle-three",
])
def test_error_program(challenges, challenge_id):
    challenge = challenges[challenge_id]
    result = run_test("def wrong_name(): pass", challenge["function_name"],
                      challenge["visible_tests"][0]["args"],
                      challenge["visible_tests"][0]["expected"])
    assert result.outcome == "runtime_error"


@pytest.mark.parametrize("challenge_id", [
    "last-k-total", "count-passes", "first-n-squares", "middle-three",
])
def test_infinite_loop_is_timeout(challenges, challenge_id):
    challenge = challenges[challenge_id]
    code = f"def {challenge['function_name']}(*args):\n    while True: pass"
    result = run_test(code, challenge["function_name"],
                      challenge["visible_tests"][0]["args"],
                      challenge["visible_tests"][0]["expected"], timeout=0.4)
    assert result.outcome == "timeout"


HOSTILE_PROGRAMS = [
    "import socket\ndef last_k_total(*args): return 0",
    "def last_k_total(*args): return open('secret.txt').read()",
    "def last_k_total(*args):\n    while True: pass",
    "def last_k_total(*args): return [0] * (10 ** 9)",
    "import os\nos.fork()\ndef last_k_total(*args): return 0",
    "def last_k_total(*args): print('x' * (10 ** 9))",
    "def last_k_total(*args):\n    with open('bomb', 'w') as f: f.write('x' * (10 ** 9))",
    "def last_k_total(*args): raise SystemExit(0)",
    "def last_k_total(*args): print('passed')",
    "def last_k_total(*args): __builtins__['open']('secret.txt').read()",
    "def last_k_total(*args):\n    import socket\n    return socket.socket()",
    "def last_k_total(*args):\n    import pathlib\n    return pathlib.Path('.').iterdir()",
    "def last_k_total(*args):\n    import os\n    os.remove('challenges/last-k-total.json')",
    "def last_k_total(*args):\n    raise RuntimeError('inputs: secret hidden data')",
    "def last_k_total(*args):\n    return missing_name",
]


@pytest.mark.parametrize("code", HOSTILE_PROGRAMS)
def test_hostile_programs_are_contained_and_never_pass(code, challenges):
    challenge = challenges["last-k-total"]
    test = challenge["visible_tests"][0]
    result = run_test(code, challenge["function_name"], test["args"], test["expected"], timeout=0.5)
    assert result.outcome != "passed"
    assert load_challenges(ROOT / "challenges")["last-k-total"]["id"] == "last-k-total"
