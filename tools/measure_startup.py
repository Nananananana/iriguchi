"""Measure what starting a Python GUI process costs, cold.

    python tools/measure_startup.py

Each stage is a fresh subprocess, timed end to end, seven times. The minimum is
reported alongside the median because the minimum is the honest floor -- it is
the run where nothing else on the machine interfered -- and the median is what a
person would actually see.

This measures the *cold* path. ``docs/adr/0008-the-invariant-is-the-warm-path.md``
is the decision that this is the wrong thing to gate a build on: a resident tray
process pays it once, at login. It is measured anyway, because the number is
what rejected the original specification's 1 ms target.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time

RUNS = 7

STAGES = (
    ("bare interpreter", "pass"),
    ("import tkinter", "import tkinter"),
    (
        "Tk() window realised",
        "import tkinter; r = tkinter.Tk(); r.update_idletasks(); r.update(); r.destroy()",
    ),
)


def bench(code: str, runs: int = RUNS) -> tuple[float, float]:
    """Return (min, median) wall-clock milliseconds for `python -c code`."""
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        # Not user input: `code` is a literal from STAGES above.
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", code],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        timings.append((time.perf_counter() - started) * 1000)
    return min(timings), statistics.median(timings)


def main() -> int:
    print(f"python {sys.version.split()[0]}, {RUNS} runs per stage")
    for label, code in STAGES:
        low, mid = bench(code)
        print(f"{label:<22} min {low:>4.0f} ms   median {mid:>4.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
