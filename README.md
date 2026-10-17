# Drishta / Debug Dojo - Python Practice Platform

Debug Dojo is a FastAPI-backed Python debugging practice environment. It includes a dependency-free browser frontend, challenge navigation, sandboxed submissions, deterministic explanations, progressive hints, learner progress, and an optional server-side OpenRouter explanation enhancement.

## Configuration

Copy [`.env.example`](.env.example:1) to [`.env`](.env:1) for local configuration. Process environment variables override `.env`; built-in defaults apply last, including `OPENROUTER_MODEL=openrouter/free`. Set `AI_OUTPUT_ENHANCEMENT=false` to disable provider calls. The key remains server-side and is never returned to the browser, logged, or stored in SQLite. The normal local flow has no operator-token prompt.

## Start Phase 5 in WSL Ubuntu

Open **Ubuntu** (WSL), then navigate to the project:

```bash
cd ~/project
```

Activate the existing virtual environment:

```bash
source .venv/bin/activate
```

Start the application with the repository's supported launcher:

```bash
python run.py
```

[`run.py`](run.py:1) starts Uvicorn for [`dojo.api:app`](dojo/api.py:28) on `127.0.0.1:8000`. FastAPI serves the frontend from the same application: `/` serves `frontend/index.html`, and `/frontend/app.js` plus `/frontend/styles.css` serve its assets. Open this URL in a browser:

```text
http://localhost:8000/
```

The frontend calls the same-origin API endpoints, including `GET /api/challenges`, `GET /api/ai-status`, `POST /api/submit`, `POST /api/hint`, and `GET /api/learner/{learner_id}`. Submission outcomes, mistake tags, hints, mastery, and history remain deterministic; an optional enhanced explanation is displayed separately when OpenRouter succeeds.

### Stop the server

Return to the Ubuntu terminal running the server and press:

```text
Ctrl+C
```

If port `8000` is already in use, stop the existing server before running `python run.py` again.

## Test

From `~/project`, with `.venv` activated, run:

```bash
python -m pytest -q -rs
```

The test suite covers the challenge loader, sandbox runner, API behavior, hints, learner model, and Phase 5 compatibility behavior.

Learner code is executed in a fresh child for every test. Expected values and hidden tests remain in the parent process, and hidden results contain no test details.

Example learner profile request:

```bash
curl http://localhost:8000/api/learner/demo_learner
```

## `Made By Shubhh :D`
