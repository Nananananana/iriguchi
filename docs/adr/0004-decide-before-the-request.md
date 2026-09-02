# 4. The decision is made before the request, from query features, by rules

**Status:** accepted

## Context

The 2026 survey on dynamic routing and cascading frames the design space on three
axes: **when** the decision is made (before the request, during inference, or
after a first response), **what** feeds it (query features, model metadata, past
performance), and **how** it is computed (rules, classifiers, reinforcement
learning, cascades).

Almost every published router sits at the expensive, accurate end: a learned
classifier — RouteLLM's preference-data router, BEST-Route's DeBERTa-v3-small
difficulty head — or a cascade that judges a first response before escalating.
They measurably beat rules on cost-quality.

They also cannot be read. A person cannot look at a set of learned weights and
know why their client's name went to a datacentre.

## Decision

iriguchi is pinned at the cheap end of all three axes.

**When: before the request. Always.** A decision made after a first response is
a decision made after the text was already sent. Whatever a cascade buys, it
cannot buy back a byte that has left.

**What: query features only.** No model call in the deciding path. No history,
no learned weights, no embedding of the prompt, no call to anything.

**How: rules.** Every rule is readable, and every rule that fires names itself
in the decision — see [ADR-0006](0006-every-decision-carries-its-reasons.md).

The complexity features are the ones the literature already found computable
before any model runs: length, language and script mix, code markers, requested
output shape, rare-word rate, and multi-step markers.

## Consequences

The deciding path has no way to send anything, and that is checked rather than
promised: `import-linter`'s `no-network` contract forbids `socket`, `ssl`,
`http`, `urllib` and `asyncio` throughout the domain, the ports, the application
and the non-adapter infrastructure. A test additionally poisons `socket.socket`
and asserts a full dry-run decision completes.

Decision latency is bounded by string scanning, so it is gated from v0.1 rather
than deferred.

The whole router can be explained to a lawyer, a doctor or a security reviewer
in the time it takes to read the rules. For the audiences this project names,
that is the feature.

## What it costs

Accuracy, and **less of it than this ADR claimed.**

The sentence here used to read: *the learned routers are better at the
cost-quality trade and will stay better, and no amount of rule-writing closes
that gap.* That was a claim about a magnitude, with no magnitude, and about
permanence — and it did rhetorical work, because it made the decision look like
a sacrifice.

It has now been measured, and the measurement does not support it.
`docs/measurements.md` has the table. Over the 21 generated cases, at
temperature 0, against four locally available models in two framings:

    always answering `low`        66.7%
    **the rules, today**          **81.0%**
    eight model configurations    28.6% to 90.5%

**No configuration is decidably better than the rules. Four are decidably
worse. Six sit inside the floor**, where one case is 4.76 points and a
difference under three cases cannot be read at all. The two that look like wins,
+9.5 and +4.8, are both inside it.

**And both tie the rules on the cases a router exists for.** Two thirds of the
corpus is `low`, which the trivial baseline takes for free; on the seven `moderate`
and `high` cases the rules get 5, and so do each of the two apparent winners.
Their entire margin is in the majority class.

**The wording of the question moved a model by up to nine cases; model size did
not move it monotonically at all** -- briefed, the 7B beats the 8B beats the 14B.

So the honest cost is: **the rules are not measurably behind on this corpus, and
this ADR previously said they were, permanently.** The correction matters more
than the number, because the number cannot decide anything here — the reason
below is auditability, and a large gap would not have moved it either. What the
measurement stops is this ADR borrowing the *form* of evidence for a decision
that does not rest on evidence.

What the measurement does not settle: 21 cases, labels and rules written by the
same hand, one machine, and three of the four models from one lineage. The
caveats are in `docs/measurements.md` and belong with any figure taken from it.

The judgement is that this router's errors are not symmetric — a wrongly-cheap
route costs answer quality, a wrongly-outbound route costs a leak — and a router
a person cannot read is a router they cannot trust with the second kind.

A cascade is not forbidden forever; it is deferred to v0.3, and when it arrives
it must ask the domain whether the prompt is permitted to leave *again*, rather
than inheriting a permission granted before the first attempt.
