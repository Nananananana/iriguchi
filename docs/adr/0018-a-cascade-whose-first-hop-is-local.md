# 18. A cascade whose first hop is local

**Status:** accepted

## Context

[`feasibility.md`](../feasibility.md) F1 put a number on the complexity axis for
the first time, against 42 prompts written to test it:

| labelled ↓ / iriguchi said → | low | moderate | high |
|---|---:|---:|---:|
| **low** | **14** | 1 | 0 |
| **moderate** | 12 | **2** | 0 |
| **high** | 7 | 4 | **2** |

**42.9%, against 35.7% for always answering `low`.** `low` is nearly perfect at
14/15 and `high` is 2 of 13: eleven of the thirteen hardest prompts were kept
local, seven called `low` outright.

The cause is not a bad rule. Every escalating marker is a phrase — `prove`,
`compare`, `why`, `証明`, `比較` — so difficulty is detected **only when the
request announces it**. *"Plan the migration of this table with zero downtime,
including the rollback path and what makes it irreversible"* names no marker.

That is the residual [ADR-0004](0004-decide-before-the-request.md) predicted in
writing: semantic features need a model, this estimator is built from the
complementary half, and is "by construction the weaker of the two axes."

Adding markers until the number improves would fit 42 prompts written by the
same hand and produce no better router. The question is whether there is a
different question to ask.

## Decision

**There is: ask the local model, then look at what came back.**

A cascade replaces a prediction with an observation. *Will a 3B model manage
this?* is a guess about a hypothetical. *Did it?* is a question about an
artefact, and artefacts are far more legible than intentions.

    prompt -> route -> local answer -> judge -> escalate, or keep

### The first hop is local, and that is what keeps ADR-0004 true

ADR-0004 pins the router at "before the request, always", and its objection to a
cascade is exact:

> A decision made after a first response is a decision made after the text was
> already sent. Whatever a cascade buys, it cannot buy back a byte that has left.

Every word of that is about text **leaving the machine**. The first hop here is a
model on this machine: the prompt went nowhere, the answer came from nowhere, and
nothing crossed a boundary to inform the second decision. The invariant ADR-0004
protects is untouched and the sentence protecting it stays true as written.

The consequence is a constraint rather than a preference: **a cascade whose first
hop is external is not a cascade, it is two requests.** `may_escalate` refuses
one, and a test asserts the refusal.

### The veto is not re-litigated, and cannot be

Escalation is permitted only when the original decision **left the external
destination on the table**. Not when it would be useful; not when the answer was
disappointing. A weak answer is evidence about a model, and the finding did not
become less true because the small model struggled.

This is enforced structurally rather than by discipline: `may_escalate` is
handed the decision, the quality and the available destinations, and **is never
given the prompt.** A function that cannot see the text cannot be talked into
re-scanning it with something more permissive, or into weighing *how sensitive,
really?* against *how bad was the answer?* — which is the exact trade this
project exists to refuse. A test asserts the signature.

### The judge is rules, and has no model

The estimator has no model because ADR-0004 forbids one in the deciding path.
The judge has no model for a different and simpler reason: **a judge that needs a
large model to decide whether to call a large model has not saved anything.**

One signal is decisive — a stated refusal, because a model saying "I don't know"
has answered the question about its own adequacy. Everything else is a shape
proxy, and the shape weights follow a stated rule rather than taste:

    no shape signal crosses the threshold alone
    `repetition` plus any one other shape signal does
    any two shape signals that are not `repetition` do not

`repetition` sits highest because it is the one with no innocent explanation. A
truncated answer may be terse; an echo may be a summary; a short answer may be
right. Four identical lines is a model that has come apart.

## Consequences

**The second axis stops depending on a guess.** Nothing about the 42.9% is
fixed — the estimator still decides the *first* hop and is still weak — but the
cost of it being wrong drops, because a prompt wrongly kept local now gets a
second look based on what actually happened.

**The failure mode of the judge is quality, never safety.** A broken judge
escalates something that did not need it, or misses something that did. It cannot
cause a prompt to leave that was not already permitted to, because the gate reads
a decision made before the judge ran. That is why `JudgementError` is the least
serious of the three proposer errors and says so.

**Asymmetric thresholds, deliberately.** A false *weak* sends a prompt somewhere
larger that did not need to go — on the external route, off the machine. A false
*adequate* is a disappointing answer the person can act on themselves. Those
costs are not symmetric, so the weights are not: a single shape signal never
escalates on its own.

**The external half of a cascade is still unreachable** for anyone who is not the
author, because escalation needs mamori to protect the outbound prompt and mamori
is not on PyPI ([`feasibility.md`](../feasibility.md) F2). The local half — the
answer, the judgement, the verdict and its reason — works today and is the part
that carries the argument. F2 remains the open decision it was.

**Two bands, not three.** The complexity axis has a middle band because an
explanation benefits from distinguishing "not obviously easy" from "actually
hard". This axis answers *do we ask a bigger model*, which is a yes or a no, and
a middle band would be a third answer to a two-answer question.
