"""One-command entry point reserved for the API phase."""

from dojo.runner import sweep_stale_sandboxes

if __name__ == "__main__":
    sweep_stale_sandboxes()
    print("Debug Dojo Phase 1 is ready. Run: python -m pytest -q")
