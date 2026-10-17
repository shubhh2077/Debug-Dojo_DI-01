from __future__ import annotations

import json

from fastapi.testclient import TestClient

from dojo import llm
from dojo.api import app


def test_ai_status_route_is_registered_and_safe(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-not-returned")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    response = TestClient(app).get("/api/ai-status")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "openrouter/free"
    assert "secret-not-returned" not in json.dumps(body)
    assert "key" not in body


def test_successful_enhancement_and_rejected_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, limit): return json.dumps(self.payload).encode()

    valid = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Check the boundary cases and compare the returned value."},
        }],
    }
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response(valid))
    assert llm.polish_explanation("Template.", {"diagnosis": "wrong result"})[1] == "llm"
    assert llm.status()["state"] == "enhanced"
    assert llm.status()["reason"] == "success"

    llm._CACHE.clear()
    structured = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Check the boundary cases. "},
                {"type": "text", "text": "Compare the returned value."},
            ]},
        }],
    }
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response(structured))
    assert llm.polish_explanation("Template.", {"diagnosis": "structured result"}) == (
        "Check the boundary cases. Compare the returned value.",
        "llm",
    )

    llm._CACHE.clear()
    rejected = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "```python\nreturn x\n```"},
        }],
    }
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response(rejected))
    assert llm.polish_explanation("Template.", {"diagnosis": "wrong result"}) == ("Template.", "template")
    assert llm.status()["reason"] == "response_rejected"


def test_refusal_empty_and_malformed_responses_are_rejected(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, limit): return json.dumps(self.payload).encode()

    for payload in (
        {"choices": [{"message": {"refusal": "不能", "content": ""}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": []},
    ):
        llm._CACHE.clear()
        monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, payload=payload, **kwargs: Response(payload))
        assert llm.polish_explanation("Template.", {"diagnosis": "wrong result"}) == ("Template.", "template")
        assert llm.status()["reason"] == "response_rejected"


def test_rate_limit_uses_retry_after_without_caching_or_tight_retry(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()
    calls = []

    def rate_limited(*args, **kwargs):
        calls.append(1)
        raise llm.urllib.error.HTTPError(
            "https://openrouter.ai", 429, "rate limited", {"Retry-After": "120"}, None
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", rate_limited)
    assert llm.polish_explanation("Rate template.", {"diagnosis": "wrong result"}) == (
        "Rate template.", "template"
    )
    assert llm.status()["reason"] == "provider_rate_limited"
    assert len(calls) == 1
    assert "Rate template." not in llm._CACHE
    assert llm.polish_explanation("Rate template.", {"diagnosis": "wrong result"}) == (
        "Rate template.", "template"
    )
    assert len(calls) == 1
    assert llm.status()["enabled"] is False


def test_frontend_ai_response_rendering_and_fallback_are_explicit():
    html = open("frontend/index.html", encoding="utf-8").read()
    source = open("frontend/app.js", encoding="utf-8").read()
    assert "AI Response" in html
    assert 'data.explanation_source === "enhanced"' in source
    assert '$("enhanced-explanation").textContent = ""' in source
    assert "AI enhancement unavailable; deterministic explanation is being used." in source
    assert "AI response shown; grading remains deterministic." in source


def test_live_submission_fallback_preserves_deterministic_fields(monkeypatch):
    from dojo.api import CHALLENGES, SubmitRequest, _submit

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            llm.urllib.error.HTTPError("https://openrouter.ai", 429, "rate limited", {}, None)
        ),
    )
    result = _submit(
        SubmitRequest(
            learner_id="ai-live-path",
            challenge_id="sum-of-evens",
            code="def sum_of_evens(values):\n    return 0",
        ),
        CHALLENGES["sum-of-evens"],
    )
    assert result["explanation_source"] == "deterministic"
    assert result["enhanced_explanation"] is None
    assert result["explanation"] == result["deterministic_explanation"]
    assert llm.status()["reason"] == "provider_rate_limited"


def test_provider_failure_is_safe_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    llm._RATE_LIMIT_UNTIL = 0.0
    llm._LAST_STATUS.update(state="not_checked", reason="not_checked")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    assert llm.polish_explanation("Template.", {"diagnosis": "wrong result"}) == ("Template.", "template")
    assert llm.status()["reason"] == "provider_unavailable"


def test_frontend_handles_status_and_explanation_fields():
    source = open("frontend/app.js", encoding="utf-8").read()
    assert "/api/ai-status" in source
    assert "enhanced_explanation" in source
    assert "deterministic_explanation" in source
    assert "response_rejected" not in source
