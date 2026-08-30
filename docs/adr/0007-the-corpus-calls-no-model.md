# 7. The evaluation corpus calls no model, and the traps are the dataset

**Status:** accepted

## Context

A router with no labelled cases is an opinion. So the corpus is the project, and
two things about it have to be decided before it is built, because both are
expensive to change afterwards.

**How cases are scored.** RouterArena (ICLR 2026) scores responses by exact
match against ground truth, with no LLM judge, and the reason is in the
follow-up work: judge scoring deviated from exact match by up to 10–24 points on
knowledge tasks — larger than most of the routing gains being claimed against
it. A benchmark whose noise exceeds its signal measures the judge.

**What the cases contain.** A generated corpus of obvious cases measures nothing,
because every router passes it. tsumugi found this on its first eval run: the
adversaries are what makes a corpus able to fail a wrong implementation.

## Decision

**CI calls no model, ever.** Cases are scored by exact route match against the
label. `pytest` defaults to `-m 'not llm'`, and the model-touching tests carry
that marker.

`iriguchi eval --model NAME` is the opt-in half that does call a model. Its
numbers are never a floor and never gate a build, because they are a property of
this code *and* whichever model happened to be pulled.

**Cases are generated deterministically** by `tools/generate_cases.py`. No model,
and no random seed either: the same arguments produce byte-identical fixtures, so
a regression is a diff rather than a mystery. The fixtures are committed.

**Labels are borrowed where they already exist.** mamori's
`evaluation/data/*-core.json` holds annotated Japanese, English and Chinese
samples, every value invented and already argued over. A sample carrying an
entity is a `MUST_STAY_LOCAL` case; a negative sample is a `MAY_LEAVE` case.

**Every case plants at least one adversary:**

| Trap | Shape |
|---|---|
| Looks sensitive, is not | a public documentation URL, a fictional character, a vendor's own sample key |
| Looks trivial, is not safe | "translate this", followed by a paragraph containing an API key |
| Long and easy | a pasted log with "summarize this" — length is not difficulty |
| Short and hard | four words that no small model will answer |
| Mixed script | Japanese prose around an English code block |
| Sensitive outside the prose | the secret is in an attached tool-call payload, not the sentence |
| Near-duplicate, opposite routes | one character flips the decision, and the reason must name that character |

**Every case is verified by an oracle before it is written.** The oracle reads
only the labels, and checks the case is decidable, non-trivial, and free of
anything that looks like real personal data. A generator that plants a trap
wrongly produces a case that fails a *correct* implementation, and that failure
is expensive precisely because the instinct is to go looking in the code.

## Consequences

The report takes RouterArena's dimensions, adapted: route accuracy, **leak rate**
(`MUST_STAY_LOCAL` cases routed out — the only metric with a floor, and the floor
is zero), over-caution rate, optimal-selection rate, decision latency.

**Anything that changes routing is gated on `iriguchi eval`.** Run it before and
after. Floors are set deliberately looser than the current scores: a gate set at
today's number makes every honest experiment a build failure, and tuning to reach
a threshold is what mamori's ADR-0023 records.

## What it costs

The corpus is generated from templates, so it measures whether the rules do what
the rules intend — not whether real prompts look like the templates. It cannot
tell you the leak rate on a stranger's actual work, and nothing in it substitutes
for mamori's own detection numbers.

Refusing a judge also means the complexity axis is scored against a *label* for
what a small model can handle, not against what a small model actually did.
`eval --model` exists to check that label, and it is the half CI cannot run.
