# 8. The performance invariant is the warm path, measured

**Status:** accepted

## Context

The original specification set two invariants: **10 MB resident** and **1 ms
startup**, with a build that fails when either is exceeded.

Neither was measured. Both were measured before this decision
([`docs/measurements.md`](../measurements.md), Windows 11, CPython 3.12.8 and
3.14.6):

| | Specification | Measured |
|---|---|---|
| Resident memory | 10 MB or less | **12.8–14.2 MB** bare interpreter, **27.0–28.8 MB** with a realised Tk window |
| Startup | 1 ms or less | **32 ms** bare interpreter at best, **135 ms** to a realised Tk window at best |

The interpreter is 12.8 MB before any of this project's code loads, and process
creation is 32 ms before it starts. Neither number is a slow implementation of
the design; writing less code does not reach either one.

There is a second finding, and it is the one that decided *which* number becomes
the invariant. The memory figures are stable — they move by at most 0.4 MB
across runs and interpreters. The startup figures are not: the same operation on
the same interpreter measured 32 ms once and a 796 ms median an hour later,
because process creation on Windows is dominated by the filesystem cache and the
antivirus scanner rather than by the interpreter. A build gate on cold start
would go red for reasons unrelated to the change that triggered it.

## Decision

Keep the stance, replace the numbers, and change which number is the invariant.

The specification was measuring the wrong thing. A person does not experience
cold start — a resident tray process pays that once, at login. They experience
the **warm path**: hotkey pressed, input box visible. That is measurable in tens
of milliseconds and it is what the build gates on.

Three floors:

- **Warm popup latency** — hotkey to visible, on an already-resident process.
  The headline invariant. Set at v0.3, from a measurement of the real resident
  process.
- **Routing decision latency** — prompt in, decision out, no model. Gated from
  v0.1, because the deciding path exists from v0.1.
- **Idle resident memory** — a ceiling chosen from the measured baseline plus a
  stated headroom, not from a round number that sounded impressive.

**Floors, not targets.** Each is set well above the measurement and ratcheted
down when it is earned. A floor set at today's number makes every honest
experiment a build failure.

And the rule this decision exists to establish: **a number in a document is
measured, or it is not written** — with its residual, meaning what the
measurement does *not* say. The probes live in `tools/` and are committed,
because a measurement whose script is not committed is an anecdote.

## Consequences

`tests/test_performance.py` lands in v0.3 with the popup and memory floors, and
in v0.1 with the decision-latency floor alone. It measures a resident process
rather than a subprocess round trip, because the subprocess round trip is the
number this decision rejected.

The README will claim a warm latency and an idle footprint, and both will be
numbers someone can reproduce with a committed script on stated hardware.

## What it costs

The project gives up a striking, quotable claim — "10 MB, 1 ms" is a better line
than anything true — and it gives up the marketing distance from Electron that
the round numbers implied. iriguchi will still be an order of magnitude smaller
than an Electron shell; it will not be able to say so in one syllable.

The measurement is also one machine, one OS, two interpreter builds, and Windows
reports working set generously. It is enough to reject 10 MB. It is not enough
to set the replacement ceiling, which is why the replacement ceiling is deferred
to v0.3 rather than guessed at now.

And the warm path has its own difficulty, deferred with it: measuring "hotkey to
visible" reliably means measuring a GUI event loop from inside a test, which is
harder than timing a subprocess and easier to fool. If it turns out to be as
unstable as cold start, this decision needs revisiting rather than a floor set
generously enough to always pass.
