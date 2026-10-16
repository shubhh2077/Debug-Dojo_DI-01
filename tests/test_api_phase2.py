from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from dojo.api import app


client = TestClient(app)


def submit(challenge_id: str, code: str, learner: str = "test_user"):
    return client.post("/api/submit", json={
        "learner_id": learner, "challenge_id": challenge_id, "code": code,
    })


@pytest.mark.parametrize(("challenge", "good", "bad"), [
    ("last-k-total", "def last_k_total(m,k): return sum(m[-k:]) if k else 0",
     "def last_k_total(m,k): return sum(m[:k])"),
    ("count-passes", "def count_passes(m): return sum(x >= 40 for x in m)",
     "def count_passes(m): return sum(x > 40 for x in m)"),
    ("first-n-squares", "def first_n_squares(n): return [x*x for x in range(1,n+1)]",
     "def first_n_squares(n): return [x*x for x in range(n)]"),
])
def test_api_outcomes(challenge, good, bad):
    passing = submit(challenge, good)
    assert passing.status_code == 200
    assert all(item["outcome"] == "passed" for item in passing.json()["visible"])
    failing = submit(challenge, bad)
    assert failing.status_code == 200
    assert any(item["outcome"] == "wrong_output" for item in failing.json()["visible"])
    assert set(failing.json()["visible"][0]) == {"test", "call", "expected", "got", "outcome"}


@pytest.mark.parametrize("code, outcome", [
    ("def last_k_total(m,k): raise ValueError('bad')", "runtime_error"),
    ("def last_k_total(m,k):\n    while True: pass", "timeout"),
])
def test_api_runtime_outcomes(code, outcome):
    response = submit("last-k-total", code, "outcome_user")
    assert response.status_code == 200
    assert any(item["outcome"] == outcome for item in response.json()["visible"])


def test_api_validation():
    assert submit("missing", "def f(): return 1").status_code == 404
    assert submit("last-k-total", "x" * (20 * 1024 + 1)).status_code == 400
    assert submit("last-k-total", "def f(): return 1", "bad space").status_code == 400


def test_hidden_secrecy_and_no_traceback():
    response = submit(
        "last-k-total",
        "def last_k_total(marks, k):\n"
        "    print(marks, k)\n"
        "    raise RuntimeError(f'inputs={marks}, k={k}')",
        "secret_user",
    )
    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "hidden" in serialized
    assert "RuntimeError" not in serialized
    assert "inputs=" not in serialized
    assert "1, 2, 3" not in serialized
    for item in response.json()["hidden"]:
        assert set(item) == {"test", "outcome"}


def test_k_zero_is_not_mislabeled_as_off_by_one():
    response = submit(
        "last-k-total",
        "def last_k_total(marks, k): return sum(marks[-k:])",
        "k_zero_user",
    )
    assert response.status_code == 200
    assert response.json()["mistake_tags"] == []
    explanation = response.json()["explanation"]
    assert "zero case" in explanation
    assert "no items should be selected" in explanation
    assert "off by one" not in explanation


def test_rohan_acceptance_has_three_of_six_hidden_failures():
    response = submit(
        "last-k-total",
        "def last_k_total(marks, k):\n"
        "    return sum(marks[-k:]) if len(marks) >= k else 0",
        "rohan",
    )
    assert response.status_code == 200
    body = response.json()
    assert sum(item["outcome"] != "passed" for item in body["hidden"]) == 3
    assert "unhandled_short_input" in body["mistake_tags"]
    assert body["explanation"].count("hidden tests fail") == 1
    assert "k_larger_than_list" in body["explanation"]


@pytest.mark.parametrize(("code", "tag"), [
    ("def count_passes(m):\n    print('x')", "print_not_return"),
    ("def middle_three(items):\n    items.clear()\n    return items", "mutates_input"),
    ("def count_passes(m): return sum(x > 40 for x in m)", "boundary_comparison"),
])
def test_rule_based_detectors(code, tag):
    response = submit("count-passes" if "count_passes" in code else "middle-three", code)
    assert response.status_code == 200
    assert tag in response.json()["mistake_tags"]


def test_internal_runner_failure_is_plain_error(monkeypatch):
    import dojo.api as api
    monkeypatch.setattr(api, "run_challenge", lambda *args: (_ for _ in ()).throw(RuntimeError("secret")))
    response = submit("last-k-total", "def last_k_total(m,k): return 0")
    assert response.status_code == 500
    assert response.json() == {"detail": "submission failed"}
