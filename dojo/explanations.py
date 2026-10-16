"""Plain-language explanation templates."""

from __future__ import annotations

from typing import Any


def explain(challenge: dict[str, Any], visible: list[dict[str, Any]],
            hidden: list[dict[str, Any]], tags: list[str]) -> str:
    visible_passed = sum(r["outcome"] == "passed" for r in visible)
    hidden_failed = [r for r in hidden if r["outcome"] != "passed"]
    if not hidden_failed and visible_passed == len(visible):
        return f"All {len(visible)} visible and hidden tests pass."
    crashes = sum(r["outcome"] in {"runtime_error", "timeout"} for r in hidden_failed)
    wrong = sum(r["outcome"] == "wrong_output" for r in hidden_failed)
    kinds = [r.get("kind") for r in hidden_failed if r.get("kind")]
    unique_kinds = list(dict.fromkeys(kinds))
    kind_text = ", ".join(unique_kinds) if unique_kinds else "edge cases"
    parts = [
        f"{visible_passed} of {len(visible)} visible tests pass.",
        f"{len(hidden_failed)} hidden tests fail: {crashes} crash or time out and {wrong} give wrong results.",
        f"The failures involve {kind_text}.",
    ]
    if tags:
        parts.append("Look at: " + ", ".join(tags).replace("_", " ") + ".")
    templates = challenge.get("explanations", {})
    directions = {
        "k_zero": "Check what happens when the requested count is zero; no items should be selected.",
        "k_larger_than_list": "Check how the selection behaves when the request is larger than the available input.",
        "empty_list": "Check that an empty input is handled without indexing into it.",
        "short_input": "Check the behavior before assuming the input has the usual length.",
        "exact_boundary": "Check the comparison at the exact threshold, including the threshold itself.",
        "normal": "Trace the selection and result for an ordinary-sized input.",
    }
    if unique_kinds:
        template = templates.get(unique_kinds[0])
        if template:
            parts.append(template)
        direction = directions.get(unique_kinds[0])
        if direction:
            parts.append(direction)
    return " ".join(parts)
