from __future__ import annotations

import json

from dojo.tracing import MAX_STEPS, trace_public_case


def test_trace_starts_at_selected_function_and_maps_source_lines() -> None:
    result = trace_public_case(
        "def f(value):\n"
        "    doubled = value * 2\n"
        "    return doubled\n",
        "f",
        [3],
    )

    assert result["status"] == "completed"
    events = result["events"]
    assert events[0]["event"] == "call"
    assert events[0]["function"] == "f"
    assert events[0]["line"] == 1
    assert all(event["line"] >= 1 for event in events)
    assert [event["step"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["event"] == "return"
    assert events[-1]["return_value"] == {"type": "int", "value": "6"}


def test_trace_records_branches_loops_and_per_frame_changes() -> None:
    result = trace_public_case(
        "def inner(value):\n"
        "    return value + 1\n"
        "def f(values):\n"
        "    total = 0\n"
        "    for value in values:\n"
        "        if value > 0:\n"
        "            total += inner(value)\n"
        "    return total\n",
        "f",
        [[1, -1]],
    )

    assert result["status"] == "completed"
    events = result["events"]
    assert any(event["function"] == "inner" and event["event"] == "call" for event in events)
    assert any(event["function"] == "inner" and event["event"] == "return" for event in events)
    assert any(event["line"] == 5 for event in events)
    assert any("total" in event["changes"] for event in events)
    assert result["return_value"] == {"type": "int", "value": "2"}


def test_trace_runtime_error_keeps_observed_steps_without_details() -> None:
    result = trace_public_case(
        "def f():\n"
        "    value = 1\n"
        "    return value / 0\n",
        "f",
        [],
    )

    assert result["status"] == "runtime_error"
    assert result["events"]
    assert result["events"][0]["line"] == 1
    assert result["error"] == "execution failed"
    assert "ZeroDivisionError" not in json.dumps(result)


def test_trace_budget_is_bounded_and_marks_incomplete_run() -> None:
    result = trace_public_case(
        "def f():\n"
        "    value = 0\n"
        "    while True:\n"
        "        value += 1\n",
        "f",
        [],
        timeout=1.0,
    )

    assert result["status"] in {"truncated", "timeout"}
    assert len(result["events"]) <= MAX_STEPS
    if result["status"] == "truncated":
        assert result["truncated"] is True
