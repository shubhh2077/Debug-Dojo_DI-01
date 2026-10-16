from __future__ import annotations

from typing import Any


LEGACY_CHALLENGE_ORDER = (
    "count-passes",
    "last-k-total",
    "first-n-squares",
    "middle-three",
)


def prefer_legacy_challenge(
    candidates: list[dict[str, Any]],
    attempted: set[str],
) -> dict[str, Any] | None:
    by_id = {challenge["id"]: challenge for challenge in candidates}
    unattempted = [
        by_id[challenge_id]
        for challenge_id in LEGACY_CHALLENGE_ORDER
        if challenge_id in by_id and challenge_id not in attempted
    ]
    if unattempted:
        return unattempted[0]
    attempted_legacy = [
        by_id[challenge_id]
        for challenge_id in LEGACY_CHALLENGE_ORDER
        if challenge_id in by_id
    ]
    if attempted_legacy:
        return attempted_legacy[0]
    return min(candidates, key=lambda item: item["id"]) if candidates else None
