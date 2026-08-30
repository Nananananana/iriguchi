# 12. A decision inherits the classification of the prompt it describes

**Status:** accepted

## Context

[ADR-0006](0006-every-decision-carries-its-reasons.md) says every decision
carries its reasons, and that a `Reason` names a rule and a span and never the
matched value. That rule was written to stop the obvious failure: a router that
prints the thing it was protecting.

It is not sufficient, and mamori's ADR-0032 is where the gap is named. Working
out whether its `mamori.protection-scope/1` document could list placeholder
tokens, it reached a test — *a record may state anything derivable from the
artifact it describes, and nothing else* — and then a second finding that
matters more here than the first:

> To a reader who does not hold the document, `{"kind": "NATIONAL_ID", "count":
> 1}` is not a description of something they already have. It is a pointer to
> which file is worth taking.

A `RoutingDecision` is that shape. Rendered, it says:

```
    mamori.national-id                  40-52
```

No value. A kind, a count, and — which ADR-0032 lists as *never* derivable —
an offset and a length. For a national ID or a telephone number, the length is
most of the value's shape.

To the person who just typed the prompt, all of that is derivable from a text
they are holding, and printing it is right: it is how they check the router is
working. To anybody else it is an index of which prompts were worth reading.

**iriguchi is where this costs the most.** mamori sees the text you handed it;
tsumugi sees the folder you pointed at. iriguchi sees every prompt a person
types, including the ones they typed and deleted. A decision log here is a list
of every sensitive thing that crossed a person's keyboard, sorted by kind.

## Decision

**A `RoutingDecision`, and anything rendered from one, is classified as highly
as the prompt it describes.**

That is the rule, and it is deliberately a statement about handling rather than
a list of forbidden fields. The fields are already constrained by ADR-0006; what
this adds is that satisfying ADR-0006 does not make the result safe to put
anywhere.

Three consequences follow, and they are the whole of the decision:

**Nothing writes a decision to disk.** Not a log file, not a history, not a
cache. v0.1 renders to standard output and keeps nothing, and any future feature
that wants to persist a decision has to supersede this ADR rather than add a
flag.

**Nothing sends a decision anywhere.** When the escalation channel arrives, what
goes upstream is the protected prompt. The decision that produced it stays on
this machine — it is not telemetry, not a header, not an audit trail attached to
the request.

**A protection record read from mamori is handled the same way.** When
`mamori.protection-scope/1` is implemented and iriguchi attaches one to a
decision, it arrives already carrying this rule from ADR-0032, and iriguchi does
not relax it by putting the decision somewhere the prompt would not have gone.

## Consequences

`iriguchi doctor` and `iriguchi eval` print aggregate numbers and are unaffected:
a rate over a corpus of invented cases describes the corpus, not a person.

The evaluation report names case *ids* when it lists what leaked or was missed,
never prompts, which was already true and now has a reason attached.

There is no `--log-file`, and the absence is deliberate rather than unfinished.
An operator who wants one is asking for the artifact this ADR exists to prevent,
and the honest answer is that the thing they want to keep is the thing they
should not.

## What it costs

Debugging. A person who hits a wrong routing decision cannot send anyone the
decision — they have to reproduce it, and reproducing it means retyping a prompt
they may not want to retype. `route --explain` on an invented prompt that
triggers the same rules is the workaround, and it is worse.

It also forgoes an audit trail, which is a real thing real organisations require,
and a lawyer or a doctor may work somewhere that mandates one. This ADR does not
say such a thing must never exist; it says it is not free, cannot be added as a
flag, and needs its own decision written by somebody who has thought about where
the file lives and who can read it.
