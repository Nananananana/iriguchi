# 6. Every decision carries its reasons to the end

**Status:** accepted

## Context

A router that returns a `Route` is a router nobody can debug and nobody can
trust. "It went local" is not an answer to "why did it go local", and the
question gets asked every time the answer is worse than expected.

Retrofitting reasons is invasive. Every function on the path has to grow a
second return value, every intermediate structure has to carry it, and the
places that already threw information away have to be rewritten to keep it.
tsumugi learned this as "every discarding path carries its reason to the end",
and made it a day-one rule for exactly that reason.

## Decision

The domain's output is a `RoutingDecision`, not a `Route`. It holds:

- the `Route` chosen;
- the `Sensitivity` and the `Complexity` that produced it, separately, per
  [ADR-0003](0003-sensitivity-is-a-veto.md);
- an ordered list of `Reason`s.

A `Reason` names the rule that fired, which scanner or estimator it came from,
and the span it fired on. Not the value in the span — the span. A reason that
prints a person's name to a log has undone the point of the project, so a
`Reason` carries offsets and a rule id and never the matched text. mamori's rule
that nothing logs a value, applied here.

Every destination that sensitivity *removed* is also recorded, with the reason it
was removed. Saying why is half the answer; saying why not is the other half,
and it is the half that gets dropped.

`iriguchi route --explain` prints all of it.

## Consequences

The evaluation harness scores routes, but it can also report *which rule* was
responsible for each leak and each over-detection. That turns a corpus failure
from "the router got this wrong" into "rule `shape.digit-run` fired on span
12–24", which is the difference between a finding and a mystery.

Every rule needs an id, because an id is what lets somebody disable one without
forking the library — and what lets a `Reason` name it.

`--explain` output is asserted against golden files, so a change in reasoning is
a diff in review rather than a discovery in production.

## What it costs

Every rule has to be written with an id and a span from the start, and the
temptation to add a quick unnamed check is permanent. The `Reason` list makes
decisions bigger objects than they need to be, and the CLI has to work to keep
`--explain` readable when forty rules fire on a long paste.

Both are cheaper than the retrofit.
