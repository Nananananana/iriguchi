# 11. A port arrives with its adapter

**Status:** accepted

## Context

[The design](../proposals/0001-the-design.md), section 4, names six ports:
`SensitivityScanner`, `ComplexityEstimator`, `LocalModel`, `EscalationChannel`,
`ProvenanceSource` and `Clock`. Writing all six was the obvious first move —
they are small, they are the shape of the system, and having them in place makes
the architecture legible before any of it works.

It is also how a codebase acquires interfaces nobody can change. A protocol
written before either side of it exists is a guess about a signature. The way
you learn the guess was wrong is by writing the adapter, and by then the
protocol has been in the repository long enough to look decided: it is in the
layer diagram, the architecture test counts it, and changing it feels like
revising a design rather than correcting a draft.

mamori deferred its async, event and envelope machinery on the same reasoning
(its ADR-0007). tsumugi declined to build a prompt template *language* until a
second use needed a second shape (its ADR-0017). Both were right, and both
records exist because the alternative was tempting at the time.

## Decision

**A port is written when something implements it and something calls it.**

v0.1 builds two, because both halves exist in v0.1:

| Port | Implemented by | Called by |
|---|---|---|
| `SensitivityScanner` | the fallback scanner; mamori's adapter in v0.2 | the routing use case |
| `ComplexityEstimator` | the rules estimator | the routing use case |

The other four wait for the version that gives them an adapter:
`LocalModel` and `EscalationChannel` in v0.2, `ProvenanceSource` in v0.4. `Clock`
waits for something that needs the time, which so far nothing does — the domain
is forbidden to look at it and the router does not care what day it is.

The set of destinations a machine has is **configuration in v0.1, not a probe**.
`iriguchi route --dry-run` is told what is available; it does not go and look.
That is what lets the whole of v0.1 run with the network poisoned.

## Consequences

The layer table in `AGENTS.md` describes `ports/` as a layer with two modules in
it, which is what is true. `docs/architecture.md` still does not exist, for the
same reason.

The conformance suites in `tests/contracts.py` are written against
implementations that exist, so their clauses come from real mistakes rather than
imagined ones. The clause about offsets into normalized text is the example: it
is in the suite because that is what a scanner does when it follows mamori's
advice to normalize before matching and stops there — and the suite's docstring
says which direction of that bug it can catch and which it cannot, because
writing the failing case is what showed the difference.

## What it costs

The design document now overstates what is built, and will keep doing so until
v0.4. That is the normal condition of a proposal and `docs/README.md` says a
proposal is never evidence that something exists — but a reader who skips that
line will count six ports and find two.

It also means the shape of the system is less legible from the source tree than
it would be with six stubs in it. Somebody wanting the overview has to read the
proposal, which is exactly where the overview belongs and exactly where people
do not look.
