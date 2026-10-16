"""Load and validate challenge JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED = {"last-k-total", "count-passes", "first-n-squares", "middle-three"}
DIFFICULTIES = {"easy", "medium", "hard"}


class ChallengeError(ValueError):
    """Raised when a challenge file is malformed."""


def _validate_test(test: dict[str, Any], hidden: bool) -> None:
    if not isinstance(test.get("args"), list) or "expected" not in test:
        raise ChallengeError("each test needs args and expected")
    if hidden and not isinstance(test.get("kind"), str):
        raise ChallengeError("hidden tests need a kind")


def validate_challenge(challenge: dict[str, Any]) -> None:
    required = {
        "id", "title", "description", "difficulty", "concepts", "traps",
        "function_name", "starter_code", "visible_tests", "hidden_tests",
        "hints", "explanations",
    }
    missing = required - challenge.keys()
    if missing:
        raise ChallengeError(f"missing fields: {sorted(missing)}")
    if challenge["difficulty"] not in DIFFICULTIES:
        raise ChallengeError("invalid difficulty")
    if len(challenge["visible_tests"]) < 3 or len(challenge["hidden_tests"]) < 5:
        raise ChallengeError("challenge needs at least 3 visible and 5 hidden tests")
    for test in challenge["visible_tests"]:
        _validate_test(test, hidden=False)
    for test in challenge["hidden_tests"]:
        _validate_test(test, hidden=True)
    if not isinstance(challenge["concepts"], list) or not challenge["concepts"]:
        raise ChallengeError("concepts must be non-empty")


def load_challenges(directory: str | Path = "challenges") -> dict[str, dict[str, Any]]:
    path = Path(directory)
    challenges: dict[str, dict[str, Any]] = {}
    for filename in sorted(path.glob("*.json")):
        challenge = json.loads(filename.read_text(encoding="utf-8"))
        validate_challenge(challenge)
        if challenge["id"] in challenges:
            raise ChallengeError(f"duplicate challenge id: {challenge['id']}")
        challenges[challenge["id"]] = challenge
    if not REQUIRED.issubset(challenges):
        raise ChallengeError(f"required challenges missing: {sorted(REQUIRED - challenges.keys())}")
    return challenges
