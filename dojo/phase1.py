"""Small helpers used by the Phase 1 tests."""

from __future__ import annotations

from typing import Any

from .runner import Execution, run_challenge


def public_result(execution: Execution, test_number: int, test: dict[str, Any]) -> dict[str, Any]:
    """Shape visible output; hidden shaping is intentionally separate."""
    result = {
        "test": test_number,
        "call": test["args"],
        "expected": test["expected"],
        "got": execution.value,
        "outcome": execution.outcome,
    }
    if execution.error:
        result["error"] = execution.error
    return result


def hidden_result(execution: Execution, test_number: int) -> dict[str, Any]:
    return {"test": test_number, "outcome": execution.outcome}


def run_public_and_hidden(code: str, challenge: dict[str, Any], mode: str = "local") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visible, hidden = run_challenge(code, challenge, mode=mode)
    return (
        [public_result(result, i, test) for i, (result, test) in enumerate(zip(visible, challenge["visible_tests"]), 1)],
        [hidden_result(result, i) for i, result in enumerate(hidden, 1)],
    )
