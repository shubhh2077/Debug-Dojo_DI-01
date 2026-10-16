# Debug Dojo

Phase 2 provides the API, SQLite submissions, explanations, and rule-based detectors.

## Start

```bash
source .venv/bin/activate
python run.py
```

The server refuses to start outside Linux/WSL2 where the required `resource`
limits cannot be applied. It listens on `0.0.0.0:8000`.

## Test

```bash
source .venv/bin/activate
python -m pytest -q
```

Learner code is executed in a fresh child for every test. Expected values and
hidden tests remain in the parent process, and hidden results contain no test
details.
