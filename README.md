# Debug Dojo

Phase 1 provides the challenge loader and a per-test child-process sandbox.

## Start

```powershell
python run.py
```

The Phase 1 server is a placeholder process; the HTTP API is added in Phase 2.

## Phase 1.5 runner modes

The default `local` mode is fail-closed on Windows because Python cannot
enforce all required process limits there. `local-dev` is used only by tests
and is not a security boundary. Supported execution is Docker:

```powershell
docker build -t debug-dojo:latest .
```

Docker applies `--network none`, `--read-only`, a writable tmpfs, 128 MB
memory, 64 PIDs, 0.5 CPU, and drops all capabilities. The platform audit is
available through `dojo.runner.format_platform_audit()`.

## Test

```powershell
python -m pytest -q
```

Learner code is executed in a fresh child for every test. Expected values and
hidden tests remain in the parent process, and hidden results contain no test
details.
