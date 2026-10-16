# Debug Dojo

Phase 2 provides the API, SQLite submissions, explanations, and rule-based detectors.
Phase 4 also provides persistent learner history at
`GET /api/learner/{learner_id}`, including recurring mistakes, concept mastery,
and a next-challenge recommendation. Mastery is derived from the stored
submission records, including the hint count for each individual submission.

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

Example learner profile request:

```bash
curl http://localhost:8000/api/learner/demo_learner
```
