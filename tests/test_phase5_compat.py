from dojo.learner import build_profile


def outcome():
    return {"visible": [{"outcome": "wrong_output"}], "hidden": []}


def test_empty_profile_keeps_phase4_default_with_new_challenges():
    from dojo.api import CHALLENGES
    profile = build_profile([], CHALLENGES)
    assert profile["next_challenge"]["id"] == "count-passes"


def test_recurring_match_uses_legacy_compatible_candidate_before_new_ids():
    challenges = {
        "last-k-total": {"id": "last-k-total", "concepts": ["lists"], "traps": ["off_by_one"]},
        "middle-three": {"id": "middle-three", "concepts": ["lists"], "traps": ["off_by_one"]},
        "aaa-new": {"id": "aaa-new", "concepts": ["lists"], "traps": ["off_by_one"]},
    }
    submissions = [
        {"challenge_id": "last-k-total", "mistake_tags": ["off_by_one"], "hints_used": 0, "outcomes": outcome()},
        {"challenge_id": "first-n-squares", "mistake_tags": ["off_by_one"], "hints_used": 0, "outcomes": outcome()},
    ]
    profile = build_profile(submissions, challenges)
    assert profile["next_challenge"]["id"] == "middle-three"
