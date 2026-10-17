"""Diagnosis-first explanations that never disclose hidden test details."""
from __future__ import annotations
from typing import Any

KIND_LABELS = {
    "empty_list": "an empty input",
    "k_larger_than_list": "requesting more items than the input contains",
    "k_zero": "the zero case",
    "exact_boundary": "the exact threshold",
    "short_input": "a shorter-than-usual input",
}
TAG_LABELS = {
    "print_not_return": "printing instead of returning a result",
    "mutates_input": "changing the input",
    "unhandled_short_input": "short inputs",
    "off_by_one": "an off-by-one count",
    "boundary_comparison": "the exact boundary comparison",
}
_SHORT = {"empty_list", "short_input", "k_larger_than_list", "k_zero"}


def _failed(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if r.get("outcome") != "passed"]


def _passed(results: list[dict[str, Any]]) -> bool:
    return any(r.get("outcome") == "passed" for r in results)


def _other_passed(hidden: list[dict[str, Any]], kinds: set[str]) -> bool:
    return any(r.get("kind") not in kinds and r.get("outcome") == "passed" for r in hidden)


def _off_by_one(failed: list[dict[str, Any]]) -> bool:
    for r in failed:
        if r.get("outcome") != "wrong_output":
            continue
        expected, got = r.get("expected"), r.get("got")
        if (isinstance(expected, (int, float)) and not isinstance(expected, bool)
                and isinstance(got, (int, float)) and not isinstance(got, bool)
                and abs(expected - got) == 1):
            return True
        if isinstance(expected, list) and isinstance(got, list) and abs(len(expected) - len(got)) == 1:
            return True
    return False


def diagnose(challenge: dict[str, Any], visible: list[dict[str, Any]],
             hidden: list[dict[str, Any]]) -> str | None:
    """Select one primary cause in stable, learner-safe precedence order."""
    failed = _failed(visible + hidden)
    if not failed:
        return None
    if any(r.get("error_type") == "SyntaxError" for r in failed):
        return "syntax_error"
    if any(r.get("error_type") == "NameError" or "missing function" in r.get("error", "").lower() for r in failed):
        return "missing_function"
    if any(r.get("returned_none") and r.get("printed_output") for r in failed):
        return "print_not_return"
    if any(r.get("returned_none") and not r.get("printed_output") for r in failed):
        return "no_return"
    if any(r.get("outcome") == "timeout" for r in failed):
        return "timeout"
    if any(r.get("outcome") == "runtime_error" for r in failed):
        return "exception"
    if any(r.get("mutated_input") for r in failed) and _passed(visible + hidden):
        return "mutates_input"
    if any(r.get("kind") in _SHORT - {"k_zero"} for r in failed) and (_other_passed(hidden, _SHORT - {"k_zero"}) or any(r.get("kind") in _SHORT - {"k_zero"} and r.get("outcome") != "passed" for r in hidden) and any(r.get("outcome") == "passed" for r in visible)):
        return "input_specific"
    boundary = [r for r in failed if r.get("kind") == "exact_boundary"]
    if boundary and _other_passed(hidden, {"exact_boundary"}):
        return "boundary"
    if _off_by_one(failed) or (len(boundary) >= 2 and _other_passed(hidden, {"exact_boundary"})):
        return "off_by_one"
    if any(r.get("kind") == "k_zero" for r in failed):
        return "zero_case"
    if any(r.get("outcome") == "wrong_output" for r in failed):
        return "wrong_value"
    return None


def _focus(cause: str | None, failed: list[dict[str, Any]]) -> str:
    if cause == "syntax_error": return "fix the syntax before testing the function"
    if cause == "missing_function": return "define the required function with the expected name"
    if cause in TAG_LABELS: return TAG_LABELS[cause]
    if cause == "no_return": return "the function body, because it does not return a value yet"
    if cause == "timeout": return "the loop or computation that does not finish"
    if cause == "exception": return "the operation that raises an exception"
    if cause == "input_specific":
        labels = list(dict.fromkeys(KIND_LABELS.get(r.get("kind"), "an edge case") for r in failed if r.get("kind") in _SHORT))
        return labels[0] if len(labels) == 1 else ("requesting more items than the input contains" if "k_larger_than_list" in {r.get("kind") for r in failed} else "short or empty inputs")
    if cause == "boundary": return TAG_LABELS["boundary_comparison"]
    if cause == "zero_case": return "the zero case; no items should be selected"
    if cause == "wrong_value": return "the returned value"
    return "the failing cases and the returned value"


def explain(challenge: dict[str, Any], visible: list[dict[str, Any]],
            hidden: list[dict[str, Any]], tags: list[str]) -> str:
    visible_passed = sum(r.get("outcome") == "passed" for r in visible)
    hidden_failed = _failed(hidden)
    if not hidden_failed and visible_passed == len(visible):
        return f"All {len(visible)} visible and hidden tests pass."
    failed = _failed(visible + hidden)
    if not hidden_failed:
        return f"{visible_passed} of {len(visible)} visible tests pass. Look at {_focus(diagnose(challenge, visible, hidden), failed)}."
    crashes = sum(r.get("outcome") in {"runtime_error", "timeout"} for r in hidden_failed)
    wrong = sum(r.get("outcome") == "wrong_output" for r in hidden_failed)
    return (f"{visible_passed} of {len(visible)} visible tests pass. "
            f"{len(hidden_failed)} hidden tests fail: {crashes} crash or time out and {wrong} give wrong results. "
            f"Look at {_focus(diagnose(challenge, visible, hidden), failed)}.")
