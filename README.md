# Debug Dojo

Debug Dojo runs learner Python in isolated child processes, grades hidden tests in the parent, provides code-free hints, rule-based diagnosis, learner progress, and a public execution visualizer.

## Start

From the project root, run:

```bash
python run.py
```

The app listens on `127.0.0.1:8000`. On Windows, use WSL2 Ubuntu because the sandbox requires Linux resource limits. `run.py` loads `.env` if present without overriding variables already set in the process and prints one safe OpenRouter status line before starting the server.

## Optional OpenRouter explanations

Create a local `.env` file (it is ignored by Git):

```text
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=openrouter/free
```

The API key is read only on the server. It is never accepted by the browser, returned by an endpoint, or written to logs. Only failed submissions may send a safe diagnosis, test counts, plain-language test kinds, and the deterministic template to OpenRouter after grading. Hints, mistake tags, mastery, pass/fail, hidden data, learner code, expected values, outputs, and exception messages never use the model. Unsafe or unavailable model responses fall back to the template.

Check the configured provider once with:

```bash
python -m dojo.llm_check
```

The check reports only safe categories such as no key, bad key, no credit, missing model, rate limit, timeout, or success. Provider activity is recorded as JSON Lines in `logs/llm_log.jsonl`; `logs/` and `.env` are ignored.

## Test

```bash
python -m pytest -q -rs
```

Hidden tests and expected values stay server-side. Learner code never runs in the API process, and hints contain no code.
