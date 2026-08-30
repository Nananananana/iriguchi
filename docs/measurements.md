# Measurements

**Status: current state.** What things actually cost, on real hardware, with the
scripts that produced them.

House rule, from tsumugi: *a number in a document is measured, or it is not
written*. The original specification contained two numbers that were not — 10 MB
resident and 1 ms startup — and these are the measurements that replaced them.
See [ADR-0008](adr/0008-the-invariant-is-the-warm-path.md) for what they changed.

Environment: Windows 11 Home 10.0.26200, x86_64, on a machine that was in
ordinary use — which turns out to matter, and is the second finding below.

## Resident memory

`tools/measure_memory.py`, working set, three stages, two interpreters.

| Stage | CPython 3.12.8 | CPython 3.14.6 |
|---|---|---|
| Bare interpreter, nothing imported | **12.8 MB** | **14.2 MB** |
| After `import tkinter` | 17.3 MB | 18.8 MB |
| After `Tk()` + one `Entry`, realised | **27.0 MB** | **28.8 MB** |

Repeated across several runs and both interpreters, these move by at most
0.4 MB. This is a stable measurement.

The specification's invariant was 10 MB or less. A CPython process that has
imported nothing is 28% to 42% over it, depending on the interpreter, and a
process with a window on screen is roughly three times it. The floor is not
reachable by writing less code, because it is not our code: it is the
interpreter, and then Tcl/Tk on top of it.

## Cold start

`tools/measure_startup.py`, seven fresh subprocesses per stage, minimum and
median reported.

Four runs, taken across a session in which the machine was variously idle and
running a test suite:

| Stage | best min observed | worst median observed |
|---|---|---|
| Bare interpreter (`python -c pass`) | **32 ms** | 796 ms |
| `import tkinter` | 52 ms | 456 ms |
| `Tk()` window realised and destroyed | **135 ms** | 1130 ms |

**The spread is the finding.** The same operation on the same interpreter
measured 32 ms once and a 796 ms median an hour later. Process creation on
Windows is dominated by things that are not the interpreter — the filesystem
cache, the antivirus scanner, whatever else is running — and a build gate on
this number would go red for reasons that have nothing to do with the change
that triggered it.

The specification's invariant was 1 ms. The *best* case measured here is 32
times that for a process that does nothing, and 135 times it for one that opens
a window. One millisecond is not a slow implementation of this design; it is a
different design, in a different language.

Running inside a virtualenv with an editable install adds roughly 100 ms on top
of every figure above (`.pth` files run an import hook at startup). Worth knowing
when reading a stopwatch during development; not a property of the shipped
thing.

## Shannon entropy, and where the thresholds came from

`tools/measure_entropy.py`. Every value is invented -- a real key in a file that
measures entropy would be a poor joke.

| | length | entropy | charset | entropy rule fires |
|---|---|---|---|---|
| an `sk-` style key | 32 | **4.81** | mixed | yes |
| a base64 blob | 48 | **4.68** | mixed | yes |
| a sha256 hex digest | 64 | **3.67** | hex | yes |
| a documentation URL | 47 | 4.14 | mixed | no |
| a source file path | 48 | 3.99 | mixed | no |
| run-together English | 31 | 3.72 | mixed | no |
| a long English word | 20 | 2.95 | mixed | no |
| a repeated character | 30 | 0.00 | hex | no |
| an AWS-style key id | 20 | 3.68 | mixed | no |
| an order number | 19 | 3.28 | mixed | no |
| a card-shaped digit run | 16 | 0.34 | digits | no |
| a uuid | 36 | 3.88 | mixed | no |

Four things follow, and all four are in the code as comments:

**4.5 bits for the base64-ish charset.** It is detect-secrets' default and the
measurement agrees with it *here*: it sits above the documentation URL (4.14) and
below both real secrets (4.68, 4.81). Note how little room that is. A threshold
chosen for a 0.5-bit gap is not a robust threshold, which is why the rule also
carries a length floor and why it is one rule among several rather than the
detector.

**Hex needs its own threshold, and it has to be lower.** A hex string cannot
exceed 4.0 bits per character by construction, and a real sha256 measures 3.67 --
so a 4.5 threshold would never fire on hex at all. It is 3.0.

**Digits are excluded from the entropy rule entirely.** Ten symbols cap the
entropy at log2(10) = 3.32, so any threshold low enough to catch a numeric secret
catches every order number and epoch timestamp. detect-secrets reached the same
conclusion. The over-detection is real and it belongs to the digit-run rule,
which admits to it in its own comment rather than hiding inside a statistic.

**Entropy misses short structured keys.** `AKIAIOSFODNN7EXAMPLE` measures 3.68 --
*below the documentation URL* -- and 4.5 bits is mathematically unreachable under
23 characters anyway. Format-aware prefixes are not an optimisation on top of
entropy; they are the half that catches these at all.

## What these numbers do not say

- One machine, one OS, two interpreter builds. Linux and macOS will differ,
  probably downward, and probably not by an order of magnitude on memory.
- Working set is not private commit, and Windows reports it generously. This is
  enough to reject a 10 MB target. It is **not** enough to set the replacement
  ceiling, which is why ADR-0008 defers that to v0.3 rather than guessing now.
- Nothing here measures the **warm** path — hotkey pressed to input box visible
  on an already-resident process — which is the number ADR-0008 makes the
  invariant. That measurement does not exist yet because the resident process
  does not exist yet.
- The entropy table is twelve hand-picked tokens, not a corpus. It says the
  thresholds separate *these* twelve, which is enough to choose a starting value
  and not enough to claim a false-positive rate. The number that would be a
  claim is the over-caution rate on the evaluation corpus, and that measurement
  does not exist yet.
- The startup and memory figures do not measure iriguchi. They are the floor
  underneath it.

## The probes

- `tools/measure_memory.py` — `K32GetProcessMemoryInfo`, `WorkingSetSize`, three
  stages. Windows only, deliberately: it is the platform these numbers are from,
  and a cross-platform abstraction would hide which one you are reading.
- `tools/measure_startup.py` — subprocess round trip, seven runs, min and median.
- `tools/measure_entropy.py` — Shannon entropy and the rule's verdict, over
  twelve invented tokens.

Both are committed, because a measurement whose script is not committed is an
anecdote.
