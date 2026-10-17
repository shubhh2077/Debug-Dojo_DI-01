"""Start Debug Dojo locally or on a hosted service."""
from __future__ import annotations

import os


def _load_dotenv() -> None:
    path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip("\"'")
    except OSError:
        pass


def main() -> None:
    _load_dotenv()
    from dojo.llm import startup_line
    print(startup_line())

    import uvicorn

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run("dojo.api:app", host=host, port=port)

if __name__ == "__main__":
    main()
