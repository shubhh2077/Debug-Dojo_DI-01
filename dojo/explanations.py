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
    kind_text = ", ".join(sorted(set(kinds))) if kinds else "edge cases"
    parts = [
        f"{visible_passed} of {len(visible)} visible tests pass.",
        f"{len(hidden_failed)} hidden tests fail: {crashes} crash or time out and {wrong} give wrong results.",
        f"The failures involve {kind_text}.",
    ]
    if tags:
        parts.append("Look at: " + ", ".join(tags).replace("_", " ") + ".")
    return " ".join(parts)
