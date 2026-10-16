"""FastAPI application for Phase 2."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .detectors import detect_mistakes
from .explanations import explain
from .runner import Execution, require_resource_limits, run_challenge
from .storage import SubmissionStore
from .tests_loader import load_challenges

CHALLENGES = load_challenges("challenges")
STORE = SubmissionStore()
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
SUBMISSION_LIMIT = threading.Semaphore(3)
LEARNER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
app = FastAPI(title="Debug Dojo")


class SubmitRequest(BaseModel):
    learner_id: str
    challenge_id: str
    code: str


def _call_text(function_name: str, args: list[Any]) -> str:
    return f"{function_name}({', '.join(repr(arg) for arg in args)})"


def _execution_result(number: int, execution: Execution, test: dict[str, Any],
                      hidden: bool, function_name: str) -> dict[str, Any]:
    if hidden:
        return {"test": number, "outcome": execution.outcome}
    result = {
        "test": number,
        "call": _call_text(function_name, test["args"]),
        "expected": repr(test["expected"]),
        "got": repr(execution.value),
        "outcome": execution.outcome,
    }
    return result


def _submit(request: SubmitRequest, challenge: dict[str, Any]) -> dict[str, Any]:
    visible_exec, hidden_exec = run_challenge(request.code, challenge)
    visible = [_execution_result(i, e, test, False, challenge["function_name"])
               for i, (e, test) in enumerate(zip(visible_exec, challenge["visible_tests"]), 1)]
    hidden = [_execution_result(i, e, test, True, challenge["function_name"])
              for i, (e, test) in enumerate(zip(hidden_exec, challenge["hidden_tests"]), 1)]
    internal_visible = [
        {**item, "kind": "visible", "expected": test["expected"], "got": e.value,
         "returned_none": e.returned_none, "printed_output": e.printed_output,
         "mutated_input": e.mutated_input}
        for item, test, e in zip(visible, challenge["visible_tests"], visible_exec)
    ]
    internal_hidden = [
        {**item, "kind": test["kind"], "expected": test["expected"], "got": e.value,
         "returned_none": e.returned_none, "printed_output": e.printed_output,
         "mutated_input": e.mutated_input}
        for item, test, e in zip(hidden, challenge["hidden_tests"], hidden_exec)
    ]
    tags = detect_mistakes(internal_visible + [
        {**item, "kind": test["kind"], "expected": test["expected"], "got": e.value,
         "returned_none": e.returned_none, "printed_output": e.printed_output,
         "mutated_input": e.mutated_input}
        for item, test, e in zip(hidden, challenge["hidden_tests"], hidden_exec)
    ], internal_hidden)
    outcomes = {"visible": visible, "hidden": hidden}
    submission_id = STORE.save(request.learner_id, request.challenge_id, request.code, outcomes, tags)
    return {
        "submission_id": submission_id, "learner_id": request.learner_id,
        "challenge_id": request.challenge_id, "visible": visible, "hidden": hidden,
        "mistake_tags": tags, "explanation": explain(challenge, visible, internal_hidden, tags),
    }


@app.on_event("startup")
def startup() -> None:
    require_resource_limits()


@app.post("/api/submit")
async def submit(request: SubmitRequest) -> dict[str, Any]:
    if request.challenge_id not in CHALLENGES:
        raise HTTPException(status_code=404, detail="unknown challenge")
    if not LEARNER_RE.fullmatch(request.learner_id):
        raise HTTPException(status_code=400, detail="invalid learner_id")
    if len(request.code.encode("utf-8")) > 20 * 1024:
        raise HTTPException(status_code=400, detail="code exceeds 20 KB")
    if not SUBMISSION_LIMIT.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="too many submissions")
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(POOL, _submit, request, CHALLENGES[request.challenge_id])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="submission failed")
    finally:
        SUBMISSION_LIMIT.release()
