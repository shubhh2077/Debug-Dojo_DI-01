from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from dojo.api import app
from dojo.hints import HINTS, is_code_like, validate_hints


client = TestClient(app)


def submit(challenge_id: str, code: str, learner: str = "phase3_user") -> dict:
    response = client.post("/api/submit", json={
        "learner_id": learner, "challenge_id": challenge_id, "code": code,
    })
    assert response.status_code == 200
    return response.json()


def test_all_judge_ladders_are_four_code_free_hints():
    validate_hints()
    assert set(HINTS) == {
        "last-k-total", "count-passes", "first-n-squares", "middle-three",
    }
    assert all(len(ladder) == 4 for challenge in HINTS.values() for ladder in challenge.values())


@pytest.mark.parametrize("text", [
    "```def f(): return 1```",
    "Use last_k_total here.",
    "Use return to provide the result.",
    "Use range(1, n).",
    "Use max(a, b).",
    "value = 3",
])
def test_code_like_filter_rejects(text):
    assert is_code_like(text, "last_k_total")


@pytest.mark.parametrize("text", [
    "Check the final boundary carefully.",
    "Think about the number of items selected.",
    "Trace the small example by hand.",
])
def test_code_like_filter_allows_prose(text):
    assert not is_code_like(text, "last_k_total")


def test_hint_ladder_advances_repeats_and_refuses_solution():
    result = submit(
        "last-k-total",
        "def last_k_total(marks, k): return sum(marks[-k:]) if len(marks) >= k else 0",
        "ladder_user",
    )
    submission_id = result["submission_id"]
    hints = []
    for expected_level in range(1, 6):
        response = client.post("/api/hint", json={
            "submission_id": submission_id,
            "answer_requested": expected_level == 2,
        })
        assert response.status_code == 200
        body = response.json()
        hints.append(body["hint"])
        assert body["level"] == min(expected_level, 4)
        assert body["remaining"] == max(0, 4 - min(expected_level, 4))
        if expected_level == 2:
            assert "cannot provide the answer" in body["note"]
    assert hints[3] == hints[4]
    assert "Trace your code by hand" in client.post(
        "/api/hint", json={"submission_id": submission_id}
    ).json()["note"]


def test_hint_errors_are_explicit():
    assert client.post("/api/hint", json={"submission_id": "missing"}).status_code == 404
    passing = submit(
        "last-k-total",
        "def last_k_total(m,k): return sum(m[-k:]) if k else 0",
        "passing_hint_user",
    )
    assert client.post("/api/hint", json={"submission_id": passing["submission_id"]}).status_code == 400


@pytest.mark.parametrize(("challenge_id", "code"), [
    ("last-k-total", "def last_k_total(marks, k): return sum(marks[-k:]) if len(marks) >= k else 0"),
    ("count-passes", "def count_passes(m): return sum(x > 40 for x in m)"),
    ("first-n-squares", "def first_n_squares(n): return [x*x for x in range(n)]"),
    ("middle-three", "def middle_three(items): return items[:3]"),
])
def test_hint_text_does_not_fix_the_failing_submission(challenge_id, code):
    result = submit(challenge_id, code, f"leak_{challenge_id}")
    submission_id = result["submission_id"]
    all_hints: list[str] = []
    for _ in range(4):
        response = client.post("/api/hint", json={"submission_id": submission_id})
        if response.status_code != 200:
            break
        all_hints.append(response.json()["hint"])
    comment_code = code + "\n" + "\n".join("# " + hint for hint in all_hints)
    raw_code = code + "\n" + "\n".join(all_hints)
    comment_result = submit(challenge_id, comment_code, f"comment_{challenge_id}")
    raw_result = submit(challenge_id, raw_code, f"raw_{challenge_id}")
    assert any(item["outcome"] != "passed" for item in comment_result["hidden"])
    assert any(item["outcome"] != "passed" for item in raw_result["hidden"])
