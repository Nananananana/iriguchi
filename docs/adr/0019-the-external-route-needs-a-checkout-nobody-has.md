# 19. The external route is out of scope for v0.1, and says so

**Status:** accepted

## Context

[`feasibility.md`](../feasibility.md) F2 has been open since it was written. It
is the only finding in that document that names the owner as the one who has to
answer it, and it has been restated in three ADRs and two replies to Sora
without moving.

The finding, in one table, re-checked on 2026-09-07:

| distribution | on PyPI |
|---|---|
| `mamori` | **404** |
| `iriguchi` | 404 |
| `tsumugi` | 200 — 1.1.1, an unrelated genomics project |

`ask --external` protects an outbound prompt through mamori, and there is no
unprotected fallback by construction — *the alternative to protecting a prompt
is not sending it*. So `MamoriChannel.__init__` refuses when mamori is absent.
That refusal is correct, and it is not what this decision is about.

What it is about is the sentence a reader meets before the refusal. The remedy
iriguchi prints is:

    mamori is not on PyPI; it needs a checkout beside this one
    (uv pip install -e ../mamori)

`../mamori` resolves on a machine with both checkouts side by side. **There is
one such machine.** Everything downstream of the external destination — the
escalation channel, the protection record reader (ADR-0013), `ask`'s upstream
(ADR-0014), the outbound half of the cascade (ADR-0018), most of what ADR-0012
exists to protect — is code no user reaches.

F1 measured the other end of the same fact: the external destination is asked
for by **1.3% of the corpus** and openable by **0% of users**.

### Three options were on the table

1. **Publish mamori.** The path becomes real and the install story becomes
   `pip install iriguchi mamori`.
2. **Say it is out of scope for v0.1.** The README leads with the local router,
   the external route is documented as needing a sibling checkout, and the
   roadmap moves it to the release where mamori ships.
3. **Vendor the protection.** Rejected on sight: it would fork a security
   boundary and give iriguchi a second copy of somebody else's threat model.

## Decision

**(2). The external route is documented as requiring a sibling checkout, and
the roadmap says which release makes it reachable.**

Nothing is deleted and no behaviour changes. What changes is what the
documentation claims, in three places:

- The README's external examples are marked as needing a checkout, at the point
  where a reader would otherwise type them.
- The road table stops listing the external half as *built* without saying who
  can build it. **`built` and `reachable` are different columns**, and the table
  had one.
- F2 is closed here rather than left open, because an option chosen is not the
  same document as an option available.

This does not foreclose (1). Publishing mamori later turns a documented
prerequisite into a dependency line, and nothing here has to be undone to do it.

## Consequences

**The honest reading of v0.1 gets smaller, and more of it is true.** A router
that decides locally, refuses to send what should not be sent, and explains
both — for everybody. Plus an escalation path that works for anyone holding two
checkouts, said in those words rather than implied by an example.

**A user who installs from PyPI is no longer told to install a package that is
not there.** They were told to run `pip install mamori` until the message was
fixed; they are now told the truth, and the roadmap now agrees with the message.

**The cost is that the most interesting half of the design is v0.2's.** The
protection record reader, `ask`'s upstream, the escalation gate and the outbound
cascade are all built, all tested against a real mamori on the one machine that
has it, and all unreachable for a reader. Calling that *v0.1, built* was the
part that was not true.

**What would reverse this.** mamori on PyPI. At that point `siblings` becomes a
real extra, the roadmap row moves, and this ADR is superseded rather than
argued with — the pattern ADR-0017 set when presidio made the fallback's miss
rate followable for the first time.

**What this does not say.** Nothing here is a claim about whether mamori
*should* be published. That is a question about a different repository and its
own readiness, and iriguchi is not the place it gets answered. This decision is
only about what iriguchi says while the answer is no.
