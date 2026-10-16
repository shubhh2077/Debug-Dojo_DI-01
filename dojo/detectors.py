"""Rule-based behavioural mistake detectors."""

from __future__ import annotations

from typing import Any


def _failing(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if r["outcome"] != "passed"]


def detect_mistakes(visible: list[dict[str, Any]], hidden: list[dict[str, Any]]) -> list[str]:
    """Apply only observable rules; hidden details never leave this module."""
    all_results = visible + hidden
    failing = _failing(all_results)
    if not failing:
        return []
    tags: list[str] = []
    if any(r.get("returned_none") and r.get("printed_output") for r in failing):
        tags.append("print_not_return")
    if any(r.get("mutated_input") for r in all_results):
        tags.append("mutates_input")
    short_kinds = {"empty_list", "short_input", "k_larger_than_list"}
    if any(r.get("kind") in short_kinds for r in failing):
        tags.append("unhandled_short_input")
    boundary = [r for r in hidden if r.get("kind") == "exact_boundary"]
    if boundary and all(r["outcome"] != "passed" for r in boundary):
        other = [r for r in hidden if r.get("kind") != "exact_boundary"]
        if any(r["outcome"] == "passed" for r in other):
            tags.append("boundary_comparison")
    for result in failing:
        if result["outcome"] != "wrong_output":
            continue
        expected, got = result.get("expected"), result.get("got")
        if isinstance(expected, (int, float)) and isinstance(got, (int, float)) and abs(expected - got) == 1:
            tags.append("off_by_one")
        elif isinstance(expected, list) and isinstance(got, list) and abs(len(expected) - len(got)) == 1:
            tags.append("off_by_one")
    if not any(tag == "off_by_one" for tag in tags):
        boundary_failures = [r for r in failing if r.get("kind") in {"exact_boundary", "k_zero"}]
        if len(boundary_failures) >= 2:
            tags.append("off_by_one")
    return list(dict.fromkeys(tags))
