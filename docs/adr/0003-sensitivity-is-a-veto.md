# 3. Sensitivity is a veto, complexity is a preference, and they are never one score

**Status:** accepted

## Context

The obvious implementation of a two-axis router is one score. Weight sensitivity,
weight difficulty, add, threshold. It is easy to write, easy to tune, and every
routing paper that reports a cost-quality curve is doing some version of it.

It is also the bug. Once the two axes are one number, a sufficiently difficult
prompt can out-vote a sensitivity finding, because addition has no way to
express "this destination is not available at any price". The tuning that makes
the router perform better on hard questions is exactly the tuning that makes it
leak.

PRISM (AAAI 2026) keeps them ordered for the same reason: profile entity-level
sensitivity first, gate second. The 2026 hybrid-architecture practice states the
failure mode plainly — a sensitive request that cannot be served locally must
return an error, not quietly go to the cloud.

## Decision

Two evaluations, in a fixed order, with different types.

**Sensitivity produces a set of permitted destinations.** It only ever removes.
It is not a number that participates in any comparison with a quality or cost
signal.

**Complexity chooses among what remains.** If sensitivity left only
`{LOCAL}`, complexity is computed for the record and for `--explain`, and it
changes nothing.

The types enforce it: `RoutingPolicy.decide` takes a `Sensitivity` and a
`Complexity` and there is no arithmetic between them anywhere in the codebase. A
`Complexity` cannot be constructed into a `Sensitivity` and there is no common
scalar they both convert to.

## Consequences

"Route this to the big model because it is hard" is unrepresentable when the
prompt contains a credential. Not discouraged — unrepresentable.

The two axes can be developed, tested and measured independently, and they are:
the corpus labels sensitivity class and complexity band separately, and a
regression in one does not move the other's numbers.

`--explain` prints them separately, in that order, which is also the order a
person needs to read them in: *what was removed, then what was chosen*.

## What it costs

Some genuinely hard, genuinely non-sensitive-looking prompts stay local and get
a worse answer, because the fallback scanner over-detected. That is
[ADR-0002](0002-fail-closed.md)'s accepted error direction, and the price of
never having the other one.

It also forgoes the cost-quality frontier the learned routers optimise. iriguchi
will not top a routing leaderboard, because the leaderboards score the axis this
decision refuses to trade on.
