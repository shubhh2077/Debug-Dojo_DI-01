from __future__ import annotations

import json
from pathlib import Path

import pytest

from dojo import llm


def facts():
    return {"diagnosis": "the result does not handle a boundary case", "passed": 1, "failed": 2, "kinds": ["an empty input", "a boundary case"]}


def reset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    llm._CACHE.clear()


def test_missing_key_uses_template_and_logs_without_secret(monkeypatch, tmp_path):
    reset(monkeypatch, tmp_path)
    result = llm.polish_explanation("Look at the boundary handling.", facts())
    assert result == ("Look at the boundary handling.", "template")
    log = (tmp_path / "logs/llm_log.jsonl").read_text()
    assert "OPENROUTER_API_KEY" not in log


@pytest.mark.parametrize("answer", [None, "```python\nreturn x\n```", "Use wrong_case here.", "def solve():\n    return 1"])
def test_unsafe_provider_output_falls_back(monkeypatch, tmp_path, answer):
    reset(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key-1234")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps({"choices": [{"message": {"content": answer}}]}).encode()
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert llm.polish_explanation("Template.", facts()) == ("Template.", "template")
    assert "secret-key-1234" not in (tmp_path / "logs/llm_log.jsonl").read_text()


def test_valid_provider_output_is_used(monkeypatch, tmp_path):
    reset(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key-1234")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"model":"reported","choices":[{"message":{"content":"Check the boundary cases and compare the returned value."}}]}'
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert llm.polish_explanation("Template.", facts()) == ("Check the boundary cases and compare the returned value.", "llm")


def test_status_contains_only_safe_metadata(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key-1234")
    monkeypatch.setenv("OPENROUTER_MODEL", "model-x")
    body = llm.status()
    assert body["enabled"] is True
    assert body["model"] == "model-x"
    assert body["state"] in {"not_checked", "enhanced"}
    assert body["reason"] in {"not_checked", "success"}
    assert "secret-key-1234" not in json.dumps(body)
    assert "key" not in body


def test_dotenv_preserves_existing_environment(monkeypatch, tmp_path):
    import run
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=file-key\nOPENROUTER_MODEL=file-model\n")
    monkeypatch.setattr(run.os.path, "dirname", lambda _: str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "process-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    run._load_dotenv()
    assert run.os.environ["OPENROUTER_API_KEY"] == "process-key"
    assert run.os.environ["OPENROUTER_MODEL"] == "file-model"
