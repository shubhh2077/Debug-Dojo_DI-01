"""Optional, server-side OpenRouter explanation enhancement."""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"
MAX_PROMPT_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 16 * 1024
MAX_OUTPUT_CHARS = 600
TIMEOUT_SECONDS = 8
MAX_CONCURRENT_REQUESTS = 2
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SYSTEM = (
    "You are a patient coding tutor. Improve the supplied deterministic explanation "
    "in 2 or 3 short plain-text sentences for a beginner. Explain what to inspect and "
    "suggest a next step. Do not write code, reveal answers, mention hidden tests, "
    "invent test results, or claim execution you did not observe. Output explanation text only."
)
_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
_CACHE: dict[str, tuple[str, str]] = {}


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip().strip("\"'")
            if name and name not in os.environ:
                os.environ[name] = value
    except OSError:
        return


_load_dotenv()


def _config() -> tuple[bool, str, str]:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    enabled = os.environ.get("AI_OUTPUT_ENHANCEMENT", "true").strip().lower() not in {"0", "false", "no", "off"}
    return enabled, key, model


def status() -> dict[str, Any]:
    enabled, key, model = _config()
    return {"enabled": enabled and bool(key) and bool(_MODEL_RE.fullmatch(model)), "model": model}


def startup_line() -> str:
    enabled, key, model = _config()
    if not enabled:
        return "AI enhancement: disabled; deterministic explanations remain active"
    return "AI enhancement: configured" if key and _MODEL_RE.fullmatch(model) else "AI enhancement: unavailable; deterministic explanations remain active"


def _safe_prompt(template_text: str, facts: dict[str, Any]) -> str:
    safe = {
        "deterministic_explanation": str(template_text)[:1500],
        "diagnosis": str(facts.get("diagnosis", "an incorrect result or execution failure"))[:300],
        "passed": max(0, min(int(facts.get("passed", 0)), 100)),
        "failed": max(0, min(int(facts.get("failed", 0)), 100)),
        "public_categories": [str(item)[:100] for item in facts.get("kinds", [])[:10]],
    }
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))


def _valid(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not text or len(text) > MAX_OUTPUT_CHARS or len(text.split()) > 100 or "```" in text:
        return False
    if re.search(r"(?im)^\s*(?:def|class|return|for|while|if|import|from)\b", text):
        return False
    if re.search(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", text):
        return False
    return True


def _log(source: str, reason: str = "") -> None:
    try:
        path = Path.cwd() / "logs" / "llm_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "source": source, "reason": reason}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return


def _fallback(template_text: str, reason: str = "fallback") -> tuple[str, str]:
    _log("template", reason)
    return template_text, "template"


def polish_explanation(template_text: str, facts: dict[str, Any]) -> tuple[str, str]:
    enabled, key, model = _config()
    if not enabled or not key or not _MODEL_RE.fullmatch(model):
        return _fallback(template_text)
    prompt = _safe_prompt(template_text, facts)
    cache_key = prompt
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES or not _SEMAPHORE.acquire(blocking=False):
        result = _fallback(template_text, "request_bound")
        _CACHE[cache_key] = result
        return result
    try:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
            "max_tokens": 160,
            "temperature": 0.2,
        }, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(URL, data=payload, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "debug-dojo/1.0",
            "X-Title": "Debug Dojo",
        }, method="POST")
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return _fallback(template_text)
        data = json.loads(raw.decode("utf-8"))
        answer = data["choices"][0]["message"]["content"]
        result = (answer.strip(), "llm") if _valid(answer) else _fallback(template_text, "invalid_output")
        if result[1] == "llm":
            _log("llm")
        _CACHE[cache_key] = result
        return result
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError, KeyError, IndexError, TypeError) as exc:
        result = _fallback(template_text, type(exc).__name__)
        _CACHE[cache_key] = result
        return result
    finally:
        _SEMAPHORE.release()
