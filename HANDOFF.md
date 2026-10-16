# Debug Dojo: Handoff Report

*Tagline: Find the bug. Keep the struggle.*

**Purpose of this file:** it lets any AI coding agent (or person) resume the project with no other context. Read all of it before writing code. Where this file and the code disagree, inspect the repo, tell the owner about the difference, and do not guess.

Owner: a solo developer in a 24-hour hackathon (two teammates handle content, frontend help and slides). Agent used: VS Code Copilot.

---

## 1. The project in one paragraph

A Python practice environment that runs learner code in a restricted sandbox, reports every test separately (passed, wrong output, runtime error, timeout), explains failures in plain language, gives progressive hints that never reveal the solution, tags each failed submission with mistake categories, tracks mastery per concept, and recommends a next challenge that targets a recurring mistake. A step-by-step execution visualizer is the bonus differentiator, built last.

Story used in the demo: Rohan's `last_k_total` passes his 3 examples but fails hidden test 5. A chatbot would hand him the answer. Our tool points him to where to look, a little more if he is still stuck, and later a new problem that makes him face the same mistake.

## 2. What the judges score (this drives every decision)

Most of the score is automated and runs against our API before our 15-minute slot.

| Test | What the judges do | Full marks when |
|---|---|---|
| Sandbox red-team | About 15 hostile programs: network, files, secrets, infinite loops, memory, processes, output and disk floods, tricks against the test harness | Every one contained and never reported as passed. Server stays up. No secret or test file exposed. Next normal submission runs correctly |
| Outcome labels | 4 programs per challenge for 3 challenges: pass, wrong output, error, run forever | All 12 labels exactly right |
| Hidden-test secrecy | Programs that print or raise their inputs, hint requests, inspection of browser traffic | No hidden input, expected output, program output or exception message reaches the learner |
| Hint leakage | For 3 failing submissions, request every hint (also after asking for the answer), merge all code from the hints into the learner's code | Merged code still fails at least one hidden test |
| Recurring mistakes | A scripted learner submits about 11 programs over the 4 judge challenges | Both planted recurring mistakes named, one-off slips not named, next challenge targets a recurring mistake with a reason |
| Explanations and hints | Two judges rate 5 failures blind, 0 to 2 each on correct, specific, not giving the answer away | High average rating |

## 3. Non-negotiable rules

1. **Hidden tests stay hidden.** Never return a hidden test's input, expected output, the program's output on it, or its exception message. For hidden tests return only `{test, outcome}`. Explanations may name the kind of input ("a case where k is larger than the list"), never values. Hidden-test data lives only on the server.
2. **Learner code never runs in the API process.** Each test runs in its own child process.
3. **The parent compares.** The child only runs the learner's function and returns the value as JSON bytes. The parent compares it to the expected value. Expected values never exist inside the child. Ignore learner stdout for pass/fail. The parent never unpickles child data.
4. **Hints contain no code at all.** No code fences, no solving function names, no snippets. No "show solution" feature. If the learner asks for the answer, return the next hint plus a gentle refusal.
5. **Mistake detection is rule-based and behavioural, not AI.** An LLM, if used at all, only drafts hints offline for human review, or polishes wording given only test kind and outcome. Log every prompt and response if any LLM is used.
6. **Fail closed.** Any internal runner error becomes `runtime_error`, never `passed`. If OS limits cannot be applied, refuse to run learner code.
7. **Outcome labels** are exactly one of: `passed`, `wrong_output`, `runtime_error`, `timeout`. A run killed by a memory, output or file limit is `runtime_error` and (for visible tests only) says which limit.

## 4. Environment and workflow

- Development machine: Windows with **WSL2 Ubuntu**. The project lives at `~/project` inside Ubuntu (copied from the Windows folder). Work in VS Code connected to WSL (bottom-left says "WSL: Ubuntu").
- Python virtual environment: `source .venv/bin/activate` inside `~/project`.
- Run tests: `python -m pytest -q -rs`. Start the server: `python run.py` (after Phase 2 it starts uvicorn on 0.0.0.0:8000). Open `http://localhost:8000` from the Windows browser.
- The server runs on **Linux** because `resource.setrlimit` (CPU, memory, file size, process count, open files) does not exist on native Windows. Learners and judges only use a browser or HTTP, so their operating system does not matter.
- Git: a **private** GitHub repo (the hidden tests are inside `challenges/`, so it must not be public). Use a branch per phase (`git checkout -b phase2`).
- Stack: Python 3.11+, FastAPI, SQLite via stdlib `sqlite3`, one static frontend page. No Next.js, no auth, no microservices.

## 5. Current status: DONE

### Phase 1: challenges and sandbox runner (complete)
- Challenge JSON loader with schema validation.
- The four required challenges with full visible and hidden test sets: `last-k-total`, `count-passes`, `first-n-squares`, `middle-three`.
- Per-test child-process runner with parent-side comparison and exact outcome labels.
- Hidden-test response shaping (`{test, outcome}` only).
- Timeout handling, runtime-error classification, capped stdout/stderr, cleared environment, temp working directory, restricted imports and `open()` policy inside the child.

### Phase 1.5: hardening (complete)
- Fail-closed behaviour: missing OS limits, unknown modes, internal errors, bad child results all become `runtime_error`.
- Pipe safety: `send_bytes` / `recv_bytes` with a size cap, JSON parsed in the parent, no pickle.
- Temp directories created under the OS temp folder, process killed before cleanup, retry on deletion, stale `debug-dojo-*` sweep at startup, `.gitignore` entries added.
- Limit naming for visible tests: memory, output, file size, filesystem, resource.
- Extra hostile tests: forged result objects, infinite output, threads, forks, file deletion, huge recursion, environment reads, `SystemExit` and `BaseException`, printing "passed", overriding the learner function name. Every one checks that a normal submission works afterwards.
- A Dockerfile and a per-test Docker mode were added but are **not the plan** (see section 6).

### Verified result (on Ubuntu / WSL2)
```
52 passed in 8.15s   (nothing skipped, so the POSIX resource-limit test runs)
```
Phase 1 is considered finished. Do not keep adding sandbox features beyond the gaps listed in section 6.

### Expected repository layout (verify by inspecting it)
```
Dockerfile  README.md  run.py  challenges/  dojo/  tests/
dojo/: __init__.py, phase1.py, runner.py, tests_loader.py, docker_child.py
tests/: test_phase1.py, test_hardening.py
```

## 6. Known gaps and technical debt

1. **Remove the per-test Docker mode** and any Docker health-check or local-dev fallback code. The decision is: the server runs on Linux (WSL2 or one container holding the whole app). Keep the check that refuses to start when the `resource` module is missing, with the message "Run inside WSL2 or Docker (see README)". Keep the Dockerfile only for packaging the whole app in one container later.
2. **Network blocking is only a Python-level import block.** `setrlimit` cannot block sockets. Final hardening: run the whole app in one container where the child cannot reach the network (for example network namespace or `--network` restrictions), and add a hostile test that tries sockets.
3. **The child runs as the same OS user as the parent**, so file permissions do not protect `challenges/*.json`. The `open()` block is a soft barrier. Final hardening: make challenge files readable only by the parent user and have the child drop privileges, or run learner code as a different unprivileged user. Keep the secrecy tests passing.
4. **Check the limit-naming claim** with a memory bomb on Linux: it must report `runtime_error` with "memory limit exceeded", never a pass or a hang. Also confirm no `debug-dojo-*` directories or stray Python processes remain after the full suite (`ls /tmp | grep debug-dojo`).
5. Submissions currently run per test, not yet in parallel. Add a small thread pool and a global concurrency cap in Phase 2.

## 7. Remaining work, in order

Work one phase at a time. After each phase: run the full suite, report results and the exact run commands, commit, then stop and wait for the owner's go-ahead.

### Phase 2: API, explanations, mistake detectors (NEXT)
1. **Runner metadata.** For each test the runner returns, besides the outcome, these internal-only fields: `returned_none` (bool), `printed_output` (bool, never the content), `mutated_input` (bool, child deep-copies args before the call and compares after) and a short `error_type` (for example "IndexError"). They are for tagging only. They never decide pass/fail and are never shown for hidden tests.
2. **Storage.** SQLite file in a gitignored `data/` folder. Table `submissions`: id like `s_0001`, learner_id, challenge_id, code, created_at, outcomes JSON, mistake_tags JSON, hint_level default 0, hints_used default 0.
3. **POST /api/submit** with body `{learner_id, challenge_id, code}`. Validate: unknown challenge gives 404, code size at most 20 KB, learner_id matches a safe pattern. Run one submission's tests in a thread pool (4 workers) and guard concurrency with a semaphore (max 3 submissions). Never crash: any internal failure returns a plain JSON error with no code or test data. Response shape in section 8.
4. **Detectors** (`detectors.py`), only on failing submissions, behaviour-based:
   - `print_not_return`: failing tests where `returned_none` and `printed_output`.
   - `mutates_input`: any test with `mutated_input`.
   - `unhandled_short_input`: failing tests whose kind is empty, short or larger-than-list, especially with a runtime error.
   - `off_by_one`: wrong output where a number differs from expected by exactly 1, or a list differs in length by exactly 1, or failures cluster on boundary-size kinds.
   - `boundary_comparison`: failures only on `exact_boundary` kinds while the other kinds pass.
   A submission may carry several tags, but only when a rule fires. Passing submissions get no tags. Document every rule in `TAXONOMY.md` (one page: category, definition, detection rule, example).
5. **Explanations** (`explanations.py`): template-based, plain language, using the challenge's per-kind templates. Structure: what passed, how many hidden tests fail and how (crashes versus wrong results), which kind of input is involved, and where to look. Never include hidden expected values or outputs. No LLM calls.
6. **Tests** (FastAPI `TestClient`): exact label tests through the API (4 programs for at least 3 challenges); secrecy tests (programs that print or raise their arguments, then assert that no hidden input, expected or got value and no traceback appears anywhere in the serialized response); one buggy program per category plus a one-off slip; five hostile programs through the API each followed by a normal passing submission; the Rohan example from the brief must produce `unhandled_short_input` with 3 of 6 hidden tests failing.
7. `run.py` starts uvicorn on 0.0.0.0:8000. Update the README with run and test commands.

### Phase 3: hints
- Store hints per challenge per mistake category: 4 hints each, each more specific than the last, all code-free. Hand-write them for the four judge challenges. For the others an LLM may draft them offline and a human reviews them.
- **POST /api/hint** with `{submission_id}` returns `{hint, level, remaining, note}`. It serves the next hint on the ladder for the submission's top mistake and increments `hint_level` and `hints_used`. After the last hint, repeat the last one with a nudge to trace the code by hand. There is no solution reveal. If the learner asks for the answer, the `note` carries a gentle refusal.
- A **code-like text filter** rejects any hint with code fences, `def`, `return`, `range(`, `max(`, `min(`, assignment-like text and similar patterns. Unit-test the filter.
- **Leakage test:** for each failing sample, request all hints, append all text from the hints to the learner's code (as comments and as raw text), re-run it, and assert it still fails at least one hidden test.
- Good example ladder for `last-k-total` (from the brief): (1) "Your three examples never ask for more marks than the list holds. What should it return when k is bigger?" (2) "Work out the call with [2, 5] and k = 3 by hand. Which index does your loop start at, and what does a negative index mean in Python?" (3) "A negative index counts back from the end, so some marks get added twice. The start index must never go below zero." (4) "Python has a built-in that returns the larger of two numbers. Use it to work out the start index once, before the loop."

### Phase 4: learner model
- **Recurring mistake:** a category that appears in at least **2 different challenges**. Repeats inside one challenge do not count. One-off slips must not be named.
- **Mastery per concept** in [0, 1]: pass with no hints moves 30% of the way toward 1; pass after hints moves 15%; a failure drops 10%.
- **Next challenge:** from the concept and trap linked to a recurring mistake, choose an unmastered challenge tagged with both. The reason is plain words, for example "You hit off_by_one in two challenges, so here is one about the end of a list."
- **GET /api/learner/{learner_id}** returns `{recurring_mistakes: [{category, challenges}], mastery: {concept: 0..1}, next_challenge: {id, reason}}`.
- **Scripted-learner test:** about 11 submissions across the 4 judge challenges with two planted recurring mistakes and one one-off slip; assert exactly the two are named and the next challenge targets one of them.

### Phase 5: content and frontend
- Add 6 more challenges to reach 10, across at least 3 difficulty levels and 4 concepts. Suggestions: `average-marks`, `find-max`, `sum-of-evens`, `sorted-copy` (mutates_input trap), `count-vowels`, `second-largest`. Each needs 3 or more visible and 5 or more hidden tests with kinds, hint ladders and explanation templates.
- Frontend: dark developer-tool look (not a chat UI). Left: challenge list and problem. Centre: code editor, Run and submit, test results (visible with details, hidden with outcome and kind only). Right: explanation card with mistake tags and the hint ladder (locked steps until revealed). Bottom row: recurring mistakes, mastery bars per concept, next challenge with reason. Thin skin over the three endpoints.

### Phase 6: execution visualizer (only if time remains, about hour 18 to 21)
- Record a trace with `sys.settrace` in the sandboxed child, for **one visible test the learner picks**, only learner-code lines, capped at about 200 steps, long values shortened. **Never trace hidden tests.**
- Send the whole trace to the browser once. The frontend steps back and forward with no re-execution and no AI calls, highlights the current line, shows variables, and marks changes by comparing consecutive snapshots.
- Optional deterministic note from the trace (for example "your loop index is negative at step 3"). Remember hostile code can disable tracing, so the trace is for teaching only, never for grading.

### Phase 7: final hardening and delivery
- Run the hostile suite and the scripted-learner test one last time. Address the gaps in section 6 (network, privilege drop, container packaging).
- Write the README with a one-command start, and finalize `TAXONOMY.md`.
- Host or tunnel the API (laptop with cloudflared or ngrok, or a small VPS) and check it from another device before judging.
- Rehearse the 5-minute demo and the viva (below). **Code freeze at hour 22.**

## 8. API contract

**POST /api/submit** request `{learner_id, challenge_id, code}`. Response:
```json
{
  "submission_id": "s_0142",
  "learner_id": "rohan",
  "challenge_id": "last-k-total",
  "visible": [
    {"test": 1, "call": "last_k_total([10, 20, 30, 40], 2)", "expected": "70", "got": "70", "outcome": "passed"}
  ],
  "hidden": [
    {"test": 1, "outcome": "passed"},
    {"test": 3, "outcome": "runtime_error"},
    {"test": 4, "outcome": "wrong_output"}
  ],
  "mistake_tags": ["unhandled_short_input"],
  "explanation": "All 3 visible tests pass, but 3 of the 6 hidden tests fail: one crashes and two give the wrong total. All three are cases where k is larger than the number of marks. Your loop starts at len(marks) - k, which is negative then."
}
```

**POST /api/hint** request `{submission_id}`, response `{hint, level, remaining, note}`.

**GET /api/learner/{learner_id}** response `{recurring_mistakes, mastery, next_challenge}`.

## 9. Challenge file format (JSON in `challenges/`)

Fields: `id`, `title`, `description`, `difficulty` (easy, medium, hard), `concepts[]`, `traps[]` (mistake categories the challenge is designed to catch), `function_name`, `starter_code`, `visible_tests[]` (args, expected), `hidden_tests[]` (args, expected, kind), `hints` (per mistake category: 4 code-free hints), `explanations` (per test kind: a plain-language template).

Hidden-test kinds to cover where relevant: `empty_list`, `k_larger_than_list`, `k_zero`, `exact_boundary`, `short_input`, `normal`.

The four judge challenges must match exactly:

| Challenge | Signature | Returns | Inputs |
|---|---|---|---|
| last-k-total | `last_k_total(marks, k)` | Total of the last k marks, or of all marks if k is larger than the list | marks: list of integers, possibly empty; k: integer, 0 or more |
| count-passes | `count_passes(marks)` | How many marks are 40 or more | marks: list of integers, possibly empty |
| first-n-squares | `first_n_squares(n)` | The list [1, 4, 9, ..., n^2], or [] when n is 0 | n: integer, 0 or more |
| middle-three | `middle_three(items)` | The middle three items as a list, or the whole list if fewer than 3 items | items: list of odd length, or with fewer than 3 items |

## 10. Mistake taxonomy (the five required, kept distinct; more may be added)

| Category | Detection |
|---|---|
| off_by_one | Result differs by exactly one element or iteration, or failures cluster on boundary-size kinds |
| unhandled_short_input | Failure or crash on empty or too-short input kinds |
| print_not_return | Function returned None while it printed output |
| boundary_comparison | Fails only at the exact threshold value (for example a mark of exactly 40) |
| mutates_input | Input differs from a deep copy taken before the call |

## 11. Demo and viva preparation

**5-minute demo:** (1) story of Rohan and the chatbot trap; (2) submit buggy `last_k_total`, show visible passes and hidden outcomes with no values; (3) open the visualizer and watch the loop index go negative; (4) reveal two hints, no code in them; (5) fix the code, everything passes, mastery moves; (6) show recurring mistakes and the next challenge with its reason; (7) show a hostile program contained and the server still serving; (8) close: the exam has no chatbot.

**Viva questions to rehearse:** why a server-side sandbox instead of browser Pyodide (hidden tests would reach the browser, nothing to red-team); how hidden tests stay secret even if code prints its inputs (parent-side comparison, hidden output discarded); how `print("passed")` or `sys.exit(0)` tricks fail (parent compares the returned value, exit is a runtime error); how hints are guaranteed code-free (pre-written, filtered, merge test); what the LLM sees and what is logged; what happens if the LLM is down (nothing, hints are pre-written); how a recurring mistake differs from a one-off slip (2 different challenges).

## 12. Deliverables checklist

- [ ] Repository with a README and one command that starts everything
- [ ] Live URL or a laptop the judges can use, with the API endpoints reachable from the start of judging
- [ ] One-page mistake taxonomy and how each category is detected (`TAXONOMY.md`)
- [ ] Log of every AI prompt and response, if any LLM is used at runtime
- [ ] Hostile-program suite and scripted-learner test passing
- [ ] 5-minute demo and viva rehearsed
- [ ] Pseudonymous learner accounts only (no real student data)

## 13. Working agreements for the AI agent

- Inspect the repo before changing anything. Keep changes small and do not touch unrelated files.
- One phase at a time. Plan in about 5 lines, build, run the full suite, report exact commands and results, then stop and wait.
- Every security decision gets a short comment. Small modules, type hints.
- Never weaken a secrecy or sandbox test to make it pass. If a test fails, fix the code and tell the owner.
- Do not add dependencies beyond FastAPI, uvicorn and pytest without asking.
- If something in this file looks wrong or the code disagrees, say so before proceeding.

## 14. Prompt to resume with a new AI

> I am building "Debug Dojo" for a 24-hour hackathon. Read HANDOFF.md in the repo root completely. Then inspect the repository and tell me, in 10 lines or fewer, what is done, what differs from the file, and your plan for the next phase. Work on one phase at a time, run the full test suite after each phase, report exact commands and results, and wait for my go-ahead before the next phase. The server runs on Linux (WSL2 Ubuntu). Start with the first phase not yet marked complete.
