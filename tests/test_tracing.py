from __future__ import annotations

import json
from pathlib import Path

import pytest

from dojo.tracing import MAX_STEPS, trace_public_case
from dojo.tests_loader import load_challenges

ROOT = Path(__file__).parents[1]


def test_trace_captures_lines_locals_and_changes():
    result = trace_public_case(
        "def f(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item\n"
        "    return total\n",
        "f",
        [[1, 2, 3]],
    )
    assert result["status"] == "completed"
    assert result["events"]
    assert len(result["events"]) <= MAX_STEPS
    assert any("total" in event["locals"] for event in result["events"])
    assert any(event["changes"] for event in result["events"])
    assert result["return_value"] == {"type": "int", "value": "6"}


def test_trace_is_bounded_for_infinite_loop():
    result = trace_public_case("def f():\n    while True:\n        pass\n", "f", [], timeout=1.0)
    assert result["status"] in {"truncated", "timeout"}
    assert len(result["events"]) <= MAX_STEPS


def test_trace_rejects_files_and_does_not_leak_error_details():
    result = trace_public_case(
        "def f():\n    return open('../challenges/last-k-total.json').read()\n",
        "f",
        [],
    )
    assert result["status"] == "runtime_error"
    serialized = json.dumps(result)
    assert "last-k-total" not in serialized
    assert "challenges" not in serialized


def test_trace_does_not_return_arbitrary_object_contents():
    result = trace_public_case(
        "class Secret:\n"
        "    def __repr__(self): return 'PRIVATE-DATA'\n"
        "def f(): return Secret()\n",
        "f",
        [],
    )
    assert result["status"] == "completed"
    assert "PRIVATE-DATA" not in json.dumps(result)
    assert result["return_value"]["value"] == "<value unavailable>"


def test_trace_code_limit_and_syntax_error_are_safe():
    too_large = trace_public_case("x" * (20 * 1024 + 1), "f", [])
    assert too_large["status"] == "runtime_error"
    assert too_large["error"] == "code limit exceeded"

    syntax = trace_public_case("def f(:", "f", [])
    assert syntax["status"] == "runtime_error"
    assert syntax["error"] == "execution failed"
    assert "line" not in json.dumps(syntax).lower()


@pytest.mark.parametrize("challenge_id", ["last-k-total", "count-passes"])
def test_real_public_case_can_be_traced_without_hidden_data(challenge_id: str):
    challenge = load_challenges(ROOT / "challenges")[challenge_id]
    test = challenge["visible_tests"][0]
    result = trace_public_case(
        challenge["starter_code"], challenge["function_name"], test["args"]
    )
    assert result["status"] in {"completed", "runtime_error"}
    serialized = json.dumps(result)
    assert "hidden_tests" not in serialized
    assert "expected" not in serialized
