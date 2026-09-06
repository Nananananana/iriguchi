"""`python -m iriguchi`, for the caller that does not have the console script.

Sora spawns its plugins as processes and does not assume an entry point is on
`PATH` -- a venv's `Scripts/` often is not, and a wheel installed with
`--target` has no scripts at all. `python -m iriguchi` is the one invocation
that works wherever the package imports, and it did not exist: the first
attempt to benchmark a call this way measured a fast failure and reported 100 ms
for a command that had not run.

Nothing here but the handoff. Every decision the command line makes lives in
`interfaces/cli/main.py`, and this file has no opinion about any of it.
"""

from __future__ import annotations

from .interfaces.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
