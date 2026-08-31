# 14. `ask` holds its own upstream, and does not go through mamori's proxy

**Status:** accepted

## Context

`docs/proposals/0001-the-design.md` §8 says v0.2 ships an `EscalationChannel`
**"pointed at mamori's OpenAI-compatible proxy rather than at an upstream
directly"**, and in the same sentence: **"iriguchi never sends raw text
anywhere, and a test asserts it."**

What shipped in [#29](https://github.com/Nananananana/iriguchi/pull/29) does
neither of those things through a proxy. `MamoriChannel` calls
`PrivacySession.protect()` in-process. **That is a divergence from the proposal,
not a completion of it**, and `iriguchi ask` is the command that makes the
divergence matter, because it is the first thing here that sends.

The proxy is real and it is good. `mamori serve --upstream https://…` listens on
`http://127.0.0.1:8100/v1/`, protects every message on the way out, restores the
reply on the way back, holds and restores placeholders split across streaming
chunks, stops a blocked credential rather than forwarding it, and binds to this
machine only. It is built on the standard library (mamori's ADR-0018). Nothing
below is a complaint about it.

## Decision

**`iriguchi ask` holds its own upstream and protects through the channel.** The
proxy is not used, and §8 is amended rather than implemented.

### The proposal asked for two things that cannot both be true

Through the proxy, iriguchi sends **unprotected** text to `127.0.0.1:8100` and
mamori protects it there. So raw text crosses a socket. It does not leave the
machine, and for mamori's own users — an application that cannot be changed —
that is exactly the right trade, because the alternative is raw text crossing
the internet.

iriguchi is not that user. It is the application, it can be changed, and it can
protect before anything is written to a socket at all. **"iriguchi never sends
raw text anywhere" is a claim the in-process channel can keep and the proxy
cannot**, unless *anywhere* quietly comes to mean *off this machine*. The
proposal named the proxy and named a property the proxy does not provide, in one
sentence, and did not notice.

### The proxy cannot return what ADR-0013 exists to read

[ADR-0013](0013-iriguchi-reads-a-protection-record-and-keeps-none.md) says
reading a protection record does one job nothing else does: iriguchi escalates
only when its own scanner said `CLEAR`, so **anything mamori protected is
something iriguchi's scanner missed**, and the person is the only one who can
act on that.

A proxy client receives an answer. It does not receive a
`mamori.protection-scope/1` record. Through the proxy the cross-check is not
degraded, it is **absent** — and it is the whole stated reason for reading a
record at all.

### And `--dry-run` would stop being able to show anything

`ports/channel.py` splits `prepare` from sending so that `iriguchi route
--explain --dry-run` can show *what would arrive* having sent nothing. The proxy
protects inside itself, at send time; the two cannot be separated from outside
it. **A guarantee that a decision can be inspected without anything leaving is
the guarantee this project is built on**, and routing it through a component
that protects only while sending gives it up.

## Consequences

`ask` needs an OpenAI-compatible client of its own, written against `urllib`,
because mamori's is inside mamori and iriguchi has no runtime dependencies. That
is duplication, and it is small: `ask` needs one anyway to reach ollama.

**Streaming restoration is not available and `ask` will not stream.** mamori's
proxy holds a placeholder arriving as `<PER`, `SON_0`, `01>` and restores it as
it passes; iriguchi's channel restores a whole answer, and `MamoriEscalation.
restore` refuses a partial restoration on purpose. Non-streaming is the honest
shape of that refusal, not a limitation to be worked around later with a buffer
that quietly reassembles.

**A person already running the proxy for their editor gains nothing here**, and
runs protection twice if they point iriguchi at it. `iriguchi ask --upstream`
should refuse an address that answers as a mamori proxy rather than protecting
already-protected text — a placeholder is a value like any other to a second
pass, and `<PERSON_001>` becoming `<PERSON_001_001>` restores in the wrong order.
That refusal is not written yet and is named here so it is not discovered.

## What it costs

The proxy is the more finished component, and this decision reimplements a
worse version of part of it: no streaming, no conversation registry, no body
cap. Every one of those is a thing mamori got right by hitting it, and iriguchi
will hit them again separately.

It also puts iriguchi in the position of holding an upstream address and an API
key, which the proxy design exists to avoid spreading. That is a real
concentration of things worth stealing, in a process whose whole argument is
that it is the small careful one.

The reason to accept both is that the alternative gives up the two properties
the project is for — nothing sent unprotected, and every decision inspectable
before anything leaves. **A more finished component that cannot make those two
promises is the wrong component, not the better one.**
