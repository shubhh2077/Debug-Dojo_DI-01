"""FastAPI application for Phase 2."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .detectors import detect_mistakes
from .explanations import explain
from .llm import polish_explanation, status as llm_status
from .hints import get_ladder
from .learner import build_profile
from .runner import Execution, require_resource_limits, run_challenge
from .storage import SubmissionStore
from .tests_loader import load_challenges
from .tracing import trace_public_case

CHALLENGES = load_challenges("challenges")
STORE = SubmissionStore()
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
SUBMISSION_LIMIT = threading.Semaphore(3)
TRACE_LIMIT = threading.Semaphore(2)
LEARNER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
app = FastAPI(title="Debug Dojo")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


class SubmitRequest(BaseModel):
    learner_id: str
    challenge_id: str
    code: str


class TraceRequest(BaseModel):
    learner_id: str
    challenge_id: str
    code: str
    visible_test: int

class HintRequest(BaseModel):
    submission_id: str
    answer_requested: bool = False
    question: str | None = None


def _call_text(function_name: str, args: list[Any]) -> str:
    return f"{function_name}({', '.join(repr(arg) for arg in args)})"


def _execution_result(number: int, execution: Execution, test: dict[str, Any], hidden: bool, function_name: str) -> dict[str, Any]:
    if hidden:
        return {"test": number, "outcome": execution.outcome}
    return {"test": number, "call": _call_text(function_name, test["args"]), "expected": repr(test["expected"]), "got": repr(execution.value), "outcome": execution.outcome}


def _submit(request: SubmitRequest, challenge: dict[str, Any]) -> dict[str, Any]:
    visible_exec, hidden_exec = run_challenge(request.code, challenge)
    visible = [_execution_result(i, e, test, False, challenge["function_name"]) for i, (e, test) in enumerate(zip(visible_exec, challenge["visible_tests"]), 1)]
    hidden = [_execution_result(i, e, test, True, challenge["function_name"]) for i, (e, test) in enumerate(zip(hidden_exec, challenge["hidden_tests"]), 1)]
    internal_visible = [{**item, "kind": "visible", "expected": test["expected"], "got": e.value, "returned_none": e.returned_none, "printed_output": e.printed_output, "mutated_input": e.mutated_input, "error": e.error, "error_type": e.error_type} for item, test, e in zip(visible, challenge["visible_tests"], visible_exec)]
    internal_hidden = [{**item, "kind": test["kind"], "expected": test["expected"], "got": e.value, "returned_none": e.returned_none, "printed_output": e.printed_output, "mutated_input": e.mutated_input, "error": e.error, "error_type": e.error_type} for item, test, e in zip(hidden, challenge["hidden_tests"], hidden_exec)]
    tags = detect_mistakes(internal_visible + internal_hidden, internal_hidden)
    outcomes = {"visible": visible, "hidden": hidden}
    submission_id = STORE.save(request.learner_id, request.challenge_id, request.code, outcomes, tags)
    template = explain(challenge, internal_visible, internal_hidden, tags)
    result = {"submission_id": submission_id, "learner_id": request.learner_id, "challenge_id": request.challenge_id, "visible": visible, "hidden": hidden, "mistake_tags": tags, "explanation": template}
    if any(item.get("outcome") != "passed" for item in visible + hidden):
        facts = {
            "diagnosis": template.split(".", 1)[0],
            "passed": sum(item.get("outcome") == "passed" for item in visible + hidden),
            "failed": sum(item.get("outcome") != "passed" for item in visible + hidden),
            "kinds": sorted({str(item.get("kind", "edge case")) for item in internal_visible + internal_hidden}),
        }
        explanation, source = polish_explanation(template, facts)
        result["explanation"] = explanation
        result["explanation_source"] = source
    return result


_PUBLIC_FIELDS = ("id", "title", "description", "difficulty", "concepts", "function_name", "starter_code", "visible_tests")


def _public_challenge(challenge: dict[str, Any]) -> dict[str, Any]:
    public = {key: challenge[key] for key in _PUBLIC_FIELDS}
    public["examples"] = [{"call": _call_text(challenge["function_name"], test["args"]), "expected": repr(test["expected"])} for test in challenge["visible_tests"]]
    public.pop("visible_tests")
    return public


@app.on_event("startup")
def startup() -> None:
    require_resource_limits()


@app.get("/")
async def frontend() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "index.html")


@app.get("/frontend/{filename}")
async def frontend_asset(filename: str) -> FileResponse:
    if filename not in {"app.js", "styles.css"}:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(FRONTEND_ROOT / filename)



@app.get("/api/ai-status")
async def ai_status() -> dict[str, Any]:
    return llm_status()

@app.get("/api/challenges")
async def challenges() -> list[dict[str, Any]]:
    return [_public_challenge(challenge) for challenge in CHALLENGES.values()]


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


@app.post("/api/trace")
async def trace(request: TraceRequest) -> dict[str, Any]:
    if request.challenge_id not in CHALLENGES:
        raise HTTPException(status_code=404, detail="unknown challenge")
    if not LEARNER_RE.fullmatch(request.learner_id):
        raise HTTPException(status_code=400, detail="invalid learner_id")
    if len(request.code.encode("utf-8")) > 20 * 1024:
        raise HTTPException(status_code=400, detail="code exceeds 20 KB")
    challenge = CHALLENGES[request.challenge_id]
    if request.visible_test < 1 or request.visible_test > len(challenge["visible_tests"]):
        raise HTTPException(status_code=400, detail="invalid visible test")
    if not TRACE_LIMIT.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="too many traces")
    try:
        test = challenge["visible_tests"][request.visible_test - 1]
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            POOL,
            trace_public_case,
            request.code,
            challenge["function_name"],
            test["args"],
        )
        safe = {
            "challenge_id": request.challenge_id,
            "visible_test": request.visible_test,
            "call": _call_text(challenge["function_name"], test["args"]),
            "status": result.get("status", "runtime_error"),
            "events": result.get("events", [])[:200],
            "return_value": result.get("return_value"),
            "truncated": bool(result.get("truncated", False)),
        }
        if result.get("error"):
            safe["error"] = str(result["error"])[:80]
        return safe
    except Exception:
        raise HTTPException(status_code=500, detail="trace failed")
    finally:
        TRACE_LIMIT.release()


@app.post("/api/hint")
async def hint(request: HintRequest) -> dict[str, Any]:
    submission = STORE.get(request.submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="unknown submission")
    tags = submission["mistake_tags"]
    if not tags:
        raise HTTPException(status_code=400, detail="submission has no detected mistake")
    category = tags[0]
    ladder = get_ladder(submission["challenge_id"], category)
    if not ladder:
        raise HTTPException(status_code=400, detail="no hint ladder for detected mistake")
    level = min(int(submission["hint_level"]) + 1, len(ladder))
    updated = STORE.advance_hint(request.submission_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="unknown submission")
    remaining = max(0, len(ladder) - level)
    note = ""
    if request.answer_requested or (request.question and "answer" in request.question.lower()):
        note = "I cannot provide the answer, but this next hint can help you investigate it."
    elif level == len(ladder) and int(submission["hint_level"]) >= len(ladder):
        note = "Trace your code by hand on a small example before changing it."
    return {"hint": ladder[level - 1], "level": level, "remaining": remaining, "note": note}


@app.get("/api/learner/{learner_id}")
async def learner(learner_id: str) -> dict[str, Any]:
    if not LEARNER_RE.fullmatch(learner_id):
        raise HTTPException(status_code=400, detail="invalid learner_id")
    return build_profile(STORE.for_learner(learner_id), CHALLENGES)
