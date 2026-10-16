"""Persistent learner history analysis and challenge recommendations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


MASTERY_THRESHOLD = 0.8


def _submission_passed(submission: dict[str, Any]) -> bool:
    outcomes = submission["outcomes"]
    return all(
        item["outcome"] == "passed"
        for group in ("visible", "hidden")
        for item in outcomes[group]
    )


def _mastery(
    submissions: list[dict[str, Any]],
    challenges: dict[str, dict[str, Any]],
) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for submission in submissions:
        challenge = challenges.get(submission["challenge_id"])
        if challenge is None:
            continue
        passed = _submission_passed(submission)
        factor = 0.15 if int(submission["hints_used"]) else 0.30
        for concept in challenge["concepts"]:
            old = scores[concept]
            scores[concept] = max(
                0.0,
                min(1.0, old + factor * (1.0 - old) if passed else old * 0.90),
            )
    return dict(sorted(scores.items()))


def _recurring_mistakes(
    submissions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    challenge_ids: dict[str, set[str]] = defaultdict(set)
    for submission in submissions:
        for category in submission["mistake_tags"]:
            challenge_ids[category].add(submission["challenge_id"])
    recurring = [
        {"category": category, "challenges": sorted(ids)}
        for category, ids in sorted(challenge_ids.items())
        if len(ids) >= 2
    ]
    return recurring, challenge_ids


def _is_mastered(challenge: dict[str, Any], mastery: dict[str, float]) -> bool:
    return bool(challenge["concepts"]) and all(
        mastery.get(concept, 0.0) >= MASTERY_THRESHOLD
        for concept in challenge["concepts"]
    )


def _next_challenge(
    submissions: list[dict[str, Any]],
    challenges: dict[str, dict[str, Any]],
    mastery: dict[str, float],
    recurring: list[dict[str, Any]],
) -> dict[str, str] | None:
    attempted = {submission["challenge_id"] for submission in submissions}
    sources: dict[str, set[str]] = defaultdict(set)
    for submission in submissions:
        for category in submission["mistake_tags"]:
            if any(item["category"] == category for item in recurring):
                sources[category].update(
                    challenges.get(submission["challenge_id"], {}).get("concepts", [])
                )

    candidates = [
        challenge for challenge in challenges.values()
        if not _is_mastered(challenge, mastery)
    ]
    if not candidates:
        return None
    attempted_ids = {challenge["id"] for challenge in candidates} & attempted
    unattempted_candidates = [
        challenge for challenge in candidates if challenge["id"] not in attempted_ids
    ]
    preferred = unattempted_candidates or candidates

    for mistake in recurring:
        category = mistake["category"]
        matching = [
            challenge for challenge in preferred
            if category in challenge.get("traps", [])
            and sources[category].intersection(challenge.get("concepts", []))
        ]
        if matching:
            challenge = sorted(matching, key=lambda item: item["id"])[0]
            return {
                "id": challenge["id"],
                "reason": (
                    f"You hit {category} in {len(mistake['challenges'])} challenges, "
                    "so here is one that targets the same concept."
                ),
            }

    pool = preferred
    challenge = sorted(
        pool, key=lambda item: (max(mastery.get(c, 0.0) for c in item["concepts"]), item["id"])
    )[0]
    return {
        "id": challenge["id"],
        "reason": "This challenge gives you practice with a concept that is not mastered yet.",
    }


def build_profile(
    submissions: list[dict[str, Any]],
    challenges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mastery = _mastery(submissions, challenges)
    recurring, _ = _recurring_mistakes(submissions)
    return {
        "recurring_mistakes": recurring,
        "mastery": mastery,
        "next_challenge": _next_challenge(submissions, challenges, mastery, recurring),
    }
