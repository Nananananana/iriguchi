# 13. iriguchi reads a protection record and keeps none

**Status:** accepted

## Context

mamori ships `mamori.protection-scope/1`: a record of what a protection did,
carrying no protected value, so that a downstream needing only to *describe* a
protection does not have to import the thing that performed one. Its ADR-0032
settles what may go in it — anything derivable from the artifact it describes —
and states the rule that matters here:

> A protection record inherits the classification of the text it describes.

The escalation channel makes iriguchi a consumer of that document, and the
question is what to do with one. **"We can now attach a record to a decision" is
not "we should."**

[ADR-0012](0012-a-decision-inherits-the-classification-of-its-prompt.md) already
says a `RoutingDecision` is classified as highly as its prompt, is never written
to disk and never sent anywhere. A record attached to one would inherit those
constraints — so the question is not whether attaching would be *unsafe*. It is
whether it would be *for* anything.

## Decision

**iriguchi reads a protection record. It attaches one to nothing and keeps
none.**

Reading it does real work, and the work is a cross-check nothing else performs.

iriguchi routes `EXTERNAL` only when its own sensitivity axis came back `CLEAR`.
mamori then protects the text on the way out — and if the record says it
protected anything at all, **iriguchi's scanner missed what mamori caught.** The
prompt still leaves safely, with placeholders where the values were. But the
decision that let it leave was made on wrong information, and the person is the
only one who can act on that.

So the record becomes a `Reason` on the escalation, naming the kinds mamori
found and the scanner that did not find them. Kinds and counts, never tokens:
the tokens are derivable from the protected text, and iriguchi does not hold the
protected text anywhere the reason goes.

Keeping the record has no such use. Nothing reads a decision back, because
nothing stores one. A record on an object that goes nowhere is disclosure with
no reader — which is the worst version of the trade, not the safest.

### What is refused

The schema's obligations are obligations, and a consumer that meets some of them
is a consumer that has not read the contract:

- **An unrecognised `contract`** is refused rather than parsed for the fields it
  happens to recognise.
- **`mode` of `surrogate` or `mixed`** is refused. iriguchi understands
  placeholders only, and the schema says so explicitly: *a consumer that
  understands only `placeholder` must refuse `surrogate` and `mixed` rather than
  read `placeholders` and conclude the document is fully enumerated.* Reading
  half a record as a whole one is the quiet failure that contract exists to
  prevent.
- **`reversible` false, or absent** — absent reads as false — is refused.
  iriguchi promised a restored answer; a masked value has no mapping behind it
  and cannot come back. Sending something that cannot be restored would be
  promising a round trip and delivering half of one.
- **mamori's own `PolicyViolationError`** is a refusal, never a fall-through.
  mamori blocks a credential rather than protecting it, and if one has reached
  the escalation path then a scanner already missed it. That is the last gate,
  and the answer to the last gate closing is not to go round it.

## Consequences

`iriguchi route --explain` on an outbound route can show the protected text that
would leave, having sent nothing. That is the first time the `--dry-run`
guarantee has anything interesting to show: not just *where* a prompt would go
but *what* would arrive.

An escalation is an object with a lifetime, because restoration needs the
session that holds the mapping. It is closed when the escalation ends, and the
mapping — the highest-value object mamori has — exists in memory for exactly as
long as the round trip.

Every refusal above leaves the prompt where it was. None of them is a
degradation to sending something less protected.

## What it costs

A record is genuinely useful to somebody assembling an audit trail across the
family, and iriguchi is the one place that sees every escalation. Declining to
keep one means iriguchi cannot be that place, and an organisation that needs
such a trail has to build it somewhere that is allowed to hold the prompts too.

Refusing `surrogate` and `mixed` outright also means a person who has configured
surrogates in mamori — a supported configuration, and the more readable one —
cannot escalate through iriguchi at all until iriguchi learns to read those
records. That is a real feature refusing to work rather than working partially,
which is the correct direction and is not free.
