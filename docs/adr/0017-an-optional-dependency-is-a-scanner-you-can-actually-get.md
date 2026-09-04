# 17. An optional dependency is a scanner you can actually get

**Status:** accepted

## Context

Two facts sat next to each other for a long time without being read together.

The first is in [`measurements.md`](../measurements.md): the built-in fallback
scanner **misses 63.5%** of the must-stay-local cases. That document argues,
correctly, that this is the fallback working as specified rather than a bug — it
has no model, and mamori's corpus is full of bare names, English names, company
names and addresses.

The second is in [`feasibility.md`](../feasibility.md) F2: **mamori is a 404 on
PyPI.** The remedy iriguchi printed beside that 63.5% was *install mamori*, and
the command it printed was `uv pip install -e ../mamori` — a relative path that
resolves on a machine with two checkouts side by side, which is one machine.

Read together they say something the project had not admitted: **every user who
is not the author has a scanner that misses most of what matters, and no way to
improve it.** The number was honest and the sentence after it was not
actionable, and an unfollowable remedy is worse than none, because it reads as a
solved problem.

`interop/presidio.py` had already been written to speak Presidio's shape without
importing it, on the reasoning that a compatibility layer should not become a
dependency. That reasoning is still right for *converting somebody else's
results*. It does nothing for a person who has no analyzer of their own.

## Decision

**iriguchi ships a `[presidio]` extra and a real Presidio adapter.**

    pip install "iriguchi[presidio]"
    python -m spacy download en_core_web_lg

Microsoft Presidio is MIT, is maintained, and is the default answer in this
space. It is a dependency worth taking, and taking it as an *extra* keeps every
promise the core made: `pip install iriguchi` still pulls nothing, and the job
that proves it by installing the wheel with no extras is unchanged.

Three things follow from the decision, and each was forced by a measurement
rather than chosen in advance.

### It is registered beside the fallback, not above it

| scanner | missed findings | over-caution |
|---|---:|---:|
| `fallback` | 63.5% | 15.7% |
| `presidio` | 45.2% | |
| **`fallback+presidio`** | **27.9%** | **60.8%** |

Presidio finds `Katherine Whitfield` where the fallback finds nothing. The
fallback finds `田中さん` where Presidio, running an English model, finds
nothing. **Neither dominates**, so a user told *Presidio is better* and given a
switch would have made their Japanese detection worse.

Hence `fallback+presidio`, a composite that unions the findings. That is sound
only because sensitivity is a veto ([ADR-0003](0003-sensitivity-is-a-veto.md)):
a union is at least as restrictive as either member, so there is no combination
rule, no weight and no disagreement to resolve. **A composite over a score would
need all three; a composite over a veto needs none.**

### The confidence stays on Presidio's side of the boundary

`RecognizerResult.score` is a real confidence and a `Finding` has nowhere to put
one, on purpose — a confidence on a veto becomes a threshold, and a threshold is
a number somebody lowers until the leak rate looks acceptable.

Discarding it silently would be worse than using it, because Presidio
deliberately emits low-confidence guesses it expects the caller to filter. So
the filtering happens **where the number means what it says**: `score_threshold`
goes to Presidio's own analyzer, the knob its authors documented and calibrated
against. What crosses into iriguchi is a decision already made.

### It will not let Presidio reach the network

`AnalyzerEngine()` calls `_download_spacy_model_if_needed`, which calls
`spacy.cli.download`, which shells out and fetches **382MB** from GitHub. No
prompt, no flag, nothing in the constructor's signature to see it coming.
Observed, not read from the source: constructing a scanner in a clean venv
printed `Downloading en-core-web-lg (382.1MiB)` from inside `__init__`.

For most libraries that is a convenience. For this one it is disqualifying.
iriguchi's claim is that the decision happens locally, before any request, and a
scanner that opens a connection **while being built** has broken that before it
reads a prompt. The model is checked with `spacy.util.is_package` first, and a
missing one is a refusal naming the exact command.

## Consequences

**The advice is followable now.** `doctor` can point at something a reader can
install. That was the whole point.

**The over-caution is real and is published rather than tuned away.** 60.8% of
may-leave prompts get held back by the composite. `DATE_TIME` alone accounts for
27.5% of it — *"by Friday"* is not a reason to keep a prompt off the network —
and removing it **costs 4.8 points of coverage**, because a date of birth is a
date. Every narrowing is a trade and none is free, so the default is every
entity, which is the fail-closed one, and `entities=` is there for somebody who
has read the table.

**Three scanners is more surface than one.** A registry with `fallback`,
`presidio`, `fallback+presidio` and `mamori` is four ways to be configured
wrong, and it was already possible to select one and silently get another — the
CLI accepted `--scanner` and dropped it. That defect is fixed and the surfaces
now agree by test rather than by inspection.

**"Zero runtime dependencies" needs the qualifier it now has.**
[ADR-0015](0015-what-zero-runtime-dependencies-promises.md) already said the
promise covers the Python dependency graph and not the OS package graph. It now
also covers *the core*, and an extra is where a user opts into a graph they can
read. Nothing installs itself; the person chooses.

**A dependency this size is a threat-model change and is stated as one.**
Presidio brings spaCy and a language model of a few hundred megabytes into a
process that sees every prompt. That is a fair price for detection and an unfair
one for a router somebody wanted to read in an afternoon, which is exactly why
it is a choice and not a default.
