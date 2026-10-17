"""Perform one harmless, safe OpenRouter connectivity check."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .llm import URL, _config


def main() -> None:
    key, model = _config()
    if not key:
        print("OpenRouter check failed: no key")
        return
    request = urllib.request.Request(
        URL,
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 4,
            "temperature": 0,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "debug-dojo/1.0",
            "X-Title": "Debug Dojo",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read(128 * 1024).decode("utf-8"))
        reported = data.get("model", model)
        print(f"OpenRouter check succeeded: {reported}")
    except urllib.error.HTTPError as exc:
        category = {401: "401 bad key", 402: "402 no credit", 404: "404 model", 429: "429 rate limit"}.get(exc.code, "HTTP error")
        print(f"OpenRouter check failed: {category}")
    except (TimeoutError, urllib.error.URLError):
        print("OpenRouter check failed: timeout or network error")
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        print("OpenRouter check failed: invalid response")


if __name__ == "__main__":
    main()
