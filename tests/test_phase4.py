from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from dojo.api import CHALLENGES, STORE, app
from dojo.learner import build_profile


client = TestClient(app)


def learner_name(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def submit(challenge_id: str, code: str, learner: str) -> dict:
    response = client.post("/api/submit", json={
        "learner_id": learner,
        "challenge_id": challenge_id,
        "code": code,
    })
    assert response.status_code == 200
    return response.json()


def test_empty_learner_is_safe_and_predictable():
    response = client.get(f"/api/learner/{learner_name('empty')}")
    assert response.status_code == 200
    body = response.json()
    assert body["recurring_mistakes"] == []
    assert body["mastery"] == {}
    assert body["next_challenge"]["id"] == "count-passes"


def test_recurring_requires_two_different_challenges():
    learner = learner_name("recurrence")
    outcomes = {"visible": [{"outcome": "wrong_output"}], "hidden": []}
    STORE.save(learner, "last-k-total", "code", outcomes, ["off_by_one"])
    STORE.save(learner, "last-k-total", "code", outcomes, ["off_by_one"])
    body = client.get(f"/api/learner/{learner}").json()
    assert "off_by_one" not in {item["category"] for item in body["recurring_mistakes"]}
    STORE.save(learner, "first-n-squares", "code", outcomes, ["off_by_one"])
    body = client.get(f"/api/learner/{learner}").json()
    categories = {item["category"]: item["challenges"] for item in body["recurring_mistakes"]}
    assert categories["off_by_one"] == ["first-n-squares", "last-k-total"]


def test_mastery_uses_the_submission_hint_count_and_stays_bounded():
    learner = learner_name("mastery")
    first = submit(
        "count-passes", "def count_passes(m): return sum(x >= 40 for x in m)", learner
    )
    assert client.post("/api/hint", json={"submission_id": first["submission_id"]}).status_code == 400
    second = submit(
        "count-passes", "def count_passes(m): return sum(x > 40 for x in m)", learner
    )
    assert client.post("/api/hint", json={"submission_id": second["submission_id"]}).status_code == 200
    body = client.get(f"/api/learner/{learner}").json()
    assert body["mastery"]["comparisons"] == 0.27
    assert 0.0 <= body["mastery"]["lists"] <= 1.0


def test_mastery_success_after_hints_uses_the_recorded_submission_count():
    submissions = [{
        "challenge_id": "count-passes",
        "mistake_tags": [],
        "hints_used": 1,
        "outcomes": {
            "visible": [{"outcome": "passed"}],
            "hidden": [{"outcome": "passed"}],
        },
    }]
    profile = build_profile(submissions, CHALLENGES)
    assert profile["mastery"]["comparisons"] == 0.15


def test_one_off_category_is_not_recurring():
    outcomes = {"visible": [{"outcome": "wrong_output"}], "hidden": []}
    submissions = [
        {"challenge_id": "last-k-total", "mistake_tags": ["k_zero"],
         "hints_used": 0, "outcomes": outcomes},
        {"challenge_id": "count-passes", "mistake_tags": ["boundary_comparison"],
         "hints_used": 0, "outcomes": outcomes},
    ]
    profile = build_profile(submissions, CHALLENGES)
    assert profile["recurring_mistakes"] == []


def test_scripted_learner_has_two_recurring_categories_and_one_one_off():
    learner = learner_name("scripted")
    outcomes = {"visible": [{"outcome": "wrong_output"}], "hidden": []}
    history = [
        ("last-k-total", ["off_by_one"]),
        ("last-k-total", ["off_by_one"]),
        ("count-passes", ["boundary_comparison"]),
        ("count-passes", ["unhandled_short_input"]),
        ("first-n-squares", ["off_by_one"]),
        ("first-n-squares", ["unhandled_short_input"]),
        ("middle-three", ["unhandled_short_input"]),
        ("middle-three", ["unhandled_short_input"]),
        ("last-k-total", []),
        ("count-passes", []),
        ("first-n-squares", []),
    ]
    for challenge_id, tags in history:
        STORE.save(learner, challenge_id, "code", outcomes, tags)

    body = client.get(f"/api/learner/{learner}").json()
    recurring = {item["category"]: set(item["challenges"])
                 for item in body["recurring_mistakes"]}
    assert set(recurring) == {"off_by_one", "unhandled_short_input"}
    assert recurring["off_by_one"] == {"first-n-squares", "last-k-total"}
    assert recurring["unhandled_short_input"] == {"count-passes", "first-n-squares", "middle-three"}
    assert body["next_challenge"]["id"] in CHALLENGES
    assert body["next_challenge"]["id"] in {"first-n-squares", "last-k-total", "middle-three"}


def test_next_challenge_matches_recurring_trap_and_concept():
    submissions = [
        {
            "challenge_id": "last-k-total",
            "mistake_tags": ["off_by_one"],
            "hints_used": 0,
            "outcomes": {"visible": [{"outcome": "wrong_output"}], "hidden": []},
        },
        {
            "challenge_id": "first-n-squares",
            "mistake_tags": ["off_by_one"],
            "hints_used": 0,
            "outcomes": {"visible": [{"outcome": "wrong_output"}], "hidden": []},
        },
    ]
    profile = build_profile(submissions, CHALLENGES)
    assert profile["recurring_mistakes"] == [{
        "category": "off_by_one",
        "challenges": ["first-n-squares", "last-k-total"],
    }]
    assert profile["next_challenge"]["id"] == "middle-three"
    assert "off_by_one" in profile["next_challenge"]["reason"]


def test_learner_api_shape_and_invalid_id():
    response = client.get(f"/api/learner/{learner_name('shape')}")
    assert response.status_code == 200
    assert set(response.json()) == {"recurring_mistakes", "mastery", "next_challenge"}
    assert client.get("/api/learner/not valid").status_code == 400
