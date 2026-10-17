"""Safe, optional OpenRouter explanation polishing."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

URL = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM = (
    "You are a patient coding tutor. Rewrite the explanation in 2 to 3 short, "
    "plain sentences for a beginner. Say what likely went wrong and where to look. "
    "Never write code, never show the fixed code or the final answer, never invent "
    "facts that are not in the input. Output only the explanation text."
)
_CACHE: dict[str, tuple[str, str]] = {}
_MAX_RAW = 128 * 1024


def _config() -> tuple[str, str]:
    return os.environ.get("OPENROUTER_API_KEY", ""), os.environ.get("OPENROUTER_MODEL", "openrouter/free")


def status() -> dict[str, Any]:
    key, model = _config()
    return {"enabled": bool(key), "model": model}


def startup_line() -> str:
    key, model = _config()
    return f"OpenRouter: configured (key ending ...{key[-4:]}, model {model})" if key else "OpenRouter: not configured, using template explanations"


def _log(prompt: str, raw: str, model: str, source: str, reason: str | None) -> None:
    path = Path("logs/llm_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "prompt": prompt, "raw_response": raw[:_MAX_RAW], "model": model, "source": source, "fallback_reason": reason}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _valid(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not text or len(text.split()) > 80 or "```" in text:
        return False
    if re.search(r"(?im)^\s*(?:def|return|for|if)\b", text):
        return False
    return not re.search(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", text)


def _prompt(template_text: str, facts: dict[str, Any]) -> str:
    safe = {"diagnosis": str(facts.get("diagnosis", "an incorrect result or execution failure")), "passed": int(facts.get("passed", 0)), "failed": int(facts.get("failed", 0)), "kinds": [str(item) for item in facts.get("kinds", [])], "template": str(template_text)}
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))


def _fallback(template_text: str, prompt: str, model: str, reason: str, raw: str = "") -> tuple[str, str]:
    result = (template_text, "template")
    _log(prompt, raw, model, result[1], reason)
    return result


def polish_explanation(template_text: str, facts: dict[str, Any]) -> tuple[str, str]:
    key, model = _config()
    prompt = _prompt(template_text, facts)
    cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    if not key:
        result = _fallback(template_text, prompt, model, "missing_key")
        _CACHE[cache_key] = result
        return result
    payload = json.dumps({"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "max_tokens": 200, "temperature": 0.3}).encode("utf-8")
    request = urllib.request.Request(URL, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "debug-dojo/1.0", "X-Title": "Debug Dojo"}, method="POST")
    raw = ""
    reported = model
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(_MAX_RAW).decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data.get("model"), str):
            reported = data["model"]
        answer = data["choices"][0]["message"]["content"]
        if _valid(answer):
            result = (answer.strip(), "llm")
            _log(prompt, raw, reported, "llm", None)
        else:
            result = _fallback(template_text, prompt, reported, "filtered_response", raw)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(_MAX_RAW).decode("utf-8", errors="replace")
        except (OSError, UnicodeError):
            pass
        reason = {401: "401_bad_key", 402: "402_no_credit", 404: "404_model", 429: "429_rate_limit"}.get(exc.code, "server_error" if exc.code >= 500 else "http_error")
        result = _fallback(template_text, prompt, model, reason, body)
    except (TimeoutError, urllib.error.URLError):
        result = _fallback(template_text, prompt, model, "timeout_or_network_error", raw)
    except (OSError, UnicodeError, ValueError, KeyError, IndexError, TypeError):
        result = _fallback(template_text, prompt, model, "invalid_response", raw)
    _CACHE[cache_key] = result
    return result
