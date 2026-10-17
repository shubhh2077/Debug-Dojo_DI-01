from __future__ import annotations

import json

from fastapi.testclient import TestClient

from dojo.api import app

client = TestClient(app)


def trace(code: str, challenge_id: str = "last-k-total", visible_test: int = 1):
    return client.post("/api/trace", json={
        "learner_id": "trace_user",
        "challenge_id": challenge_id,
        "code": code,
        "visible_test": visible_test,
    })


def test_trace_api_returns_public_trace_only():
    response = trace(
        "def last_k_total(marks, k):\n"
        "    total = 0\n"
        "    for mark in marks[-k:]:\n"
        "        total += mark\n"
        "    return total\n"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["challenge_id"] == "last-k-total"
    assert body["visible_test"] == 1
    assert body["status"] == "completed"
    assert body["events"]
    serialized = json.dumps(body)
    assert "hidden_tests" not in serialized
    assert "kind" not in serialized


def test_trace_api_validates_public_selection_and_request_limits():
    assert trace("def f(): return 1", visible_test=0).status_code == 400
    assert trace("def f(): return 1", visible_test=999).status_code == 400
    assert trace("def f(): return 1", challenge_id="missing").status_code == 404
    assert trace("x" * (20 * 1024 + 1)).status_code == 400
    assert trace("def f(): return 1", visible_test=1).status_code == 200


def test_trace_api_does_not_create_submission_or_change_learner_state():
    before = client.get("/api/learner/trace_isolation_user").json()
    response = client.post("/api/trace", json={
        "learner_id": "trace_isolation_user",
        "challenge_id": "last-k-total",
        "code": "def last_k_total(marks, k): return sum(marks)",
        "visible_test": 1,
    })
    assert response.status_code == 200
    after = client.get("/api/learner/trace_isolation_user").json()
    assert after == before


def test_trace_api_hides_error_details():
    response = trace(
        "def last_k_total(marks, k):\n"
        "    raise RuntimeError(f'private {marks} {k}')\n"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "runtime_error"
    serialized = json.dumps(body)
    assert "private" not in serialized
    assert "RuntimeError" not in serialized
    assert "hidden" not in serialized.lower()
