# 2. Fail closed: doubt routes local, and local-impossible refuses

**Status:** accepted

## Context

A router has three destinations and two directions of error.

Routing something outbound that should have stayed local is a leak. It cannot be
undone: the text is on someone else's disk, possibly in someone else's training
set, and no later correction retrieves it.

Routing something local that could safely have gone out costs answer quality.
The person notices immediately, and can say so.

These are not comparable, and a router that treats them as two sides of one
accuracy number has already made the wrong trade.

## Decision

**Every uncertainty resolves toward local.** A scanner that raised an exception,
an estimator that could not parse the input, a configuration value that did not
coerce, an entity type with no rule and no category default — each of these
yields the most restrictive route available, not the most useful one.

**A prompt that must stay local, on a machine with no local model, is
`REFUSED`.** It does not fall through to the external path. The person is told
that the request cannot be served here and why. This is the case the whole
decision exists for: a fallback that "helpfully" reaches the network when the
local model is missing converts every outage into a leak.

There is no `strict=False`, no permissive mode on the deciding path, and no
partial decision. A decision is complete or it is an exception.

## Consequences

`iriguchi doctor` matters more than it would otherwise. If the local model is
not running, a class of prompts stops working, so the tool has to say so plainly
before the person hits it mid-sentence rather than after.

The evaluation report's **leak rate** is the only metric permitted a floor of
zero. Everything else is measured and reported; that one is a gate.

An unknown configuration key is refused rather than ignored. A typo in a privacy
setting that silently does nothing is the worst available outcome: the person
believes they tightened something and did not. mamori's rule, and the reasoning
transfers unchanged.

## What it costs

Friction, deliberately placed. Someone whose ollama is not running discovers it
by being refused, and the refusal will occasionally be wrong — a prompt the
fallback scanner over-detected on, which mamori would have cleared.

That is the accepted shape of the error. [ADR-0005](0005-detection-is-a-port.md)
is how the friction is bought back, and it is bought back with precision, never
by relaxing this.
