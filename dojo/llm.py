"""Optional, server-side OpenRouter explanation enhancement."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

URL = "https://aicredits.in/v1/chat/completions"
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
_RATE_LIMIT_DEFAULT_SECONDS = 60.0
_RATE_LIMIT_MAX_SECONDS = 15 * 60.0
_RATE_LIMIT_UNTIL = 0.0
_LAST_STATUS: dict[str, str] = {"state": "not_checked", "reason": "not_checked"}


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
    valid_model = bool(_MODEL_RE.fullmatch(model))
    configured = bool(key) and valid_model
    if not enabled:
        state, reason = "disabled", "disabled_by_configuration"
    elif not key:
        state, reason = "unavailable", "missing_api_key"
    elif not valid_model:
        state, reason = "unavailable", "invalid_model"
    elif _LAST_STATUS["reason"] == "provider_rate_limited" and time.monotonic() >= _RATE_LIMIT_UNTIL:
        state, reason = "not_checked", "not_checked"
    else:
        state, reason = _LAST_STATUS["state"], _LAST_STATUS["reason"]
    return {"enabled": enabled and configured and state not in {"unavailable", "disabled"}, "model": model, "state": state, "reason": reason}


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


def _valid_reason(text: Any) -> str | None:
    if not isinstance(text, str):
        return "content_not_text"
    text = text.strip()
    if not text:
        return "empty_content"
    if len(text) > MAX_OUTPUT_CHARS:
        return "output_too_large"
    if len(text.split()) > 100:
        return "output_too_many_words"
    if "```" in text:
        return "code_fence"
    if re.search(r"(?im)^\s*(?:def|class|return|for|while|if|import|from)\b", text):
        return "code_like_output"
    if re.search(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", text):
        return "identifier_like_output"
    return None


def _valid(text: Any) -> bool:
    return _valid_reason(text) is None


def _response_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("refusal"):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                return None
            parts.append(part["text"])
        return "".join(parts)
    return None


def _response_shape(data: Any) -> str:
    if not isinstance(data, dict):
        return "not_object"
    choices = data.get("choices")
    if not isinstance(choices, list):
        return "choices_not_list"
    if not choices:
        return "choices_empty"
    first = choices[0]
    if not isinstance(first, dict):
        return "choice_not_object"
    message = first.get("message")
    if not isinstance(message, dict):
        return "message_not_object"
    if message.get("refusal"):
        return "message_refusal"
    content = message.get("content")
    if isinstance(content, str):
        return f"content_string:{len(content)}"
    if isinstance(content, list):
        return f"content_parts:{len(content)}"
    return "content_missing_or_unsupported"


def _response_shape(data: Any) -> str:
    if not isinstance(data, dict):
        return "not_object"
    choices = data.get("choices")
    if not isinstance(choices, list):
        return "choices_not_list"
    if not choices:
        return "choices_empty"
    first = choices[0]
    if not isinstance(first, dict):
        return "choice_not_object"
    message = first.get("message")
    if not isinstance(message, dict):
        return "message_not_object"
    finish = first.get("finish_reason")
    keys = ",".join(sorted(str(key) for key in message.keys()))
    if message.get("refusal"):
        return f"message_refusal;finish={finish};keys={keys}"
    content = message.get("content")
    if isinstance(content, str):
        return f"content_string:{len(content)};finish={finish};keys={keys}"
    if isinstance(content, list):
        return f"content_parts:{len(content)};finish={finish};keys={keys}"
    reasoning = message.get("reasoning")
    reasoning_type = type(reasoning).__name__ if reasoning is not None else "missing"
    return f"content_missing_or_unsupported;content_type={type(content).__name__};reasoning_type={reasoning_type};finish={finish};keys={keys}"


def _runtime_log(event: str, correlation: str, detail: str = "") -> None:
    _log("runtime", f"event={event};correlation={correlation};detail={detail}")


def _log(source: str, reason: str = "") -> None:
    try:
        path = Path.cwd() / "logs" / "llm_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "source": source, "reason": reason}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return


def _provider_error_reason(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "provider_unauthorized"
        if exc.code == 402:
            return "provider_payment_required"
        if exc.code == 404:
            return "provider_not_found"
        if exc.code == 429:
            return "provider_rate_limited"
        if 500 <= exc.code < 600:
            return "provider_server_error"
        return "provider_http_error"
    if isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return "provider_unavailable"
    if isinstance(exc, UnicodeError):
        return "response_encoding_error"
    if isinstance(exc, json.JSONDecodeError):
        return "malformed_response"
    return type(exc).__name__


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    headers = exc.headers
    value = headers.get("Retry-After") if headers is not None else None
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
        if seconds >= 0:
            return min(seconds, _RATE_LIMIT_MAX_SECONDS)
    except (TypeError, ValueError):
        pass
    try:
        target = parsedate_to_datetime(str(value))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, min((target - datetime.now(timezone.utc)).total_seconds(), _RATE_LIMIT_MAX_SECONDS))
    except (TypeError, ValueError, OverflowError):
        return None


def _fallback(template_text: str, reason: str = "fallback") -> tuple[str, str]:
    _LAST_STATUS.update(state="unavailable", reason=reason)
    _log("template", reason)
    return template_text, "template"


def polish_explanation(template_text: str, facts: dict[str, Any], correlation: str = "unknown") -> tuple[str, str]:
    global _RATE_LIMIT_UNTIL
    _runtime_log("enhancement_entered", correlation)
    enabled, key, model = _config()
    if not enabled:
        return _fallback(template_text, "disabled_by_configuration")
    if _LAST_STATUS["reason"] == "provider_rate_limited" and time.monotonic() < _RATE_LIMIT_UNTIL:
        _runtime_log("enhancement_fallback", correlation, "provider_rate_limited_cooldown")
        return _fallback(template_text, "provider_rate_limited_cooldown")
    if not key:
        return _fallback(template_text, "missing_api_key")
    if not _MODEL_RE.fullmatch(model):
        return _fallback(template_text, "invalid_model")
    prompt = _safe_prompt(template_text, facts)
    cache_key = prompt
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        result = _fallback(template_text, "request_bound")
        _CACHE[cache_key] = result
        return result
    if not _SEMAPHORE.acquire(blocking=False):
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
        _runtime_log("provider_request", correlation, f"model={model}")
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            _runtime_log("provider_response", correlation, f"status={getattr(response, 'status', 'unknown')}")
        if len(raw) > MAX_RESPONSE_BYTES:
            result = _fallback(template_text, "response_too_large")
            _CACHE[cache_key] = result
            return result
        data = json.loads(raw.decode("utf-8"))
        answer = _response_text(data)
        rejection = _valid_reason(answer)
        if rejection is not None:
            _log("response_rejected", f"{rejection};shape={_response_shape(data)}")
            result = _fallback(template_text, "response_rejected")
        else:
            result = (answer.strip(), "llm")
        if result[1] == "llm":
            _runtime_log("enhancement_accepted", correlation)
            _LAST_STATUS.update(state="enhanced", reason="success")
            _log("llm")
        _CACHE[cache_key] = result
        return result
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError, KeyError, IndexError, TypeError) as exc:
        reason = _provider_error_reason(exc)
        _runtime_log("provider_error", correlation, reason)
        if reason == "provider_rate_limited":
            retry_after = _retry_after_seconds(exc)
            delay = retry_after if retry_after is not None else _RATE_LIMIT_DEFAULT_SECONDS
            _RATE_LIMIT_UNTIL = time.monotonic() + delay
            _log("provider_error", f"status=429;retry_after={delay:g}")
        result = _fallback(template_text, reason)
        if reason not in {"provider_rate_limited", "provider_unavailable", "provider_server_error"}:
            _CACHE[cache_key] = result
        return result
    finally:
        _SEMAPHORE.release()
