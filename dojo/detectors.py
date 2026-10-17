"""Mistake tags aligned with the shared primary diagnosis."""
from __future__ import annotations
from typing import Any
from .explanations import diagnose


def detect_mistakes(visible: list[dict[str, Any]], hidden: list[dict[str, Any]]) -> list[str]:
    """Return at most one evidence-backed learner-facing tag."""
    results = visible + hidden
    if not any(r.get("outcome") == "passed" for r in results):
        return []
    cause = diagnose({}, visible, hidden)
    tags = {"print_not_return": "print_not_return", "mutates_input": "mutates_input",
            "input_specific": "unhandled_short_input", "boundary": "boundary_comparison",
            "off_by_one": "off_by_one"}
    return [tags[cause]] if cause in tags else []
