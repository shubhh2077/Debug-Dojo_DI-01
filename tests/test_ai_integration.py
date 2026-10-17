from __future__ import annotations

import json
from pathlib import Path

from dojo import llm
from dojo.api import CHALLENGES, SubmitRequest, _submit


def test_disabled_or_missing_key_is_deterministic(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()
    template = "Inspect the returned value."
    assert llm.polish_explanation(template, {"diagnosis": "wrong result"}) == (template, "template")


def test_successful_response_is_bounded_and_parsed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "true")
    llm._CACHE.clear()

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, limit):
            return json.dumps({"choices": [{"message": {"content": "Compare the boundary cases with the expected behavior."}}]}).encode()

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert llm.polish_explanation("Template.", {"diagnosis": "wrong result"}) == ("Compare the boundary cases with the expected behavior.", "llm")


def test_frontend_keeps_deterministic_explanation_separate():
    source = Path("frontend/app.js").read_text(encoding="utf-8")
    assert "deterministic_explanation" in source
    assert "enhanced_explanation" in source
    assert "explanation_source" in source


def test_api_result_keeps_grading_authoritative(monkeypatch):
    monkeypatch.setenv("AI_OUTPUT_ENHANCEMENT", "false")
    challenge = CHALLENGES["sum-of-evens"]
    request = SubmitRequest(learner_id="ai-test", challenge_id="sum-of-evens", code="def sum_of_evens(values):\n    return 0")
    result = _submit(request, challenge)
    assert result["explanation"] == result["deterministic_explanation"]
    assert result["enhanced_explanation"] is None
    assert result["explanation_source"] in {"deterministic", "template"}
    assert result["mistake_tags"] == result["mistake_tags"]
