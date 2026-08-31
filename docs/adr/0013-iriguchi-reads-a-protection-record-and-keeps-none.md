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
- **A record carrying surrogates** is refused, and the field that says so is
  `contract`, not `mode`. A record holding any surrogate declares
  `mamori.protection-scope/1+surrogate`, so a token-only consumer refuses it
  through the check it already has rather than through a rule it must remember
  every time. Reading half a record as a whole one is the quiet failure that
  contract exists to prevent.
- **Everything else the schema requires**: the eight required keys, the closed
  key set (`additionalProperties: false`), the exact shape of a `placeholders`
  entry, and the `if`/`then` forbidding surrogates under the plain contract.
  Meeting some obligations is what a consumer does when it has not read the
  contract.
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

## Amendment, 2026-08-31: which field carries the state

**As written, this ADR quoted the wrong field, and the code did what the ADR
said.** The original text refused `mode` of `surrogate` or `mixed`, citing the
schema. mamori has since moved that invariant: it split the contract identifier,
so the rule became a pair of discrete cases an `if`/`then` can state, and the
schema now says outright that `mode` is **"a summary of how values were
substituted, not a switch selecting which array to read"**, and that **"the
contract identifier, not this field, is what stops a token-only consumer from
reading half a record and believing it whole."**

iriguchi read `contract` first and so was never unsafe against a well-formed
record. It was unsafe against a malformed one, and that is the case the check
exists for: **a document declaring the plain contract while listing
surrogate-protected values was accepted**, reporting one placeholder finding and
silently dropping three surrogates. The exact failure the paragraph above
quotes.

akashi found the same shape on the same day from the other side — a draft marker
sitting on the second field a consumer reads, so a consumer selecting on `/v1`
believed it held a frozen contract and held a provisional one. **The question
that finds it is: which field do you read first, and does it carry the state?**

Measured before it was fixed: the reader accepted **eight of nine** documents
mamori's published schema rejects. Only the contract identifier fired.

`tests/test_contract_conformance.py` now holds both halves — the refusals, and a
comparison of iriguchi's hand-written key sets against the schema shipped in
mamori's wheel, in both directions. The second half is there because tsumugi
hand-wrote the same kind of constant today and it was wrong in both directions
the moment anything checked it.
