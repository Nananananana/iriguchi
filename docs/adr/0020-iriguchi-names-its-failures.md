# 20. iriguchi names its failures, and a usage error is not a refusal

**Status:** accepted

## Context

Sora is the only program that talks to all seven siblings, and therefore the
only place that can answer *is this my fault, or is something broken?* They
built the answer: `incidents.jsonl`, one line per distinct failure, folded on a
key and counted.

The key is **the name before the colon on the first line of stderr**, and they
keep nothing else — not the sentence, not a path, not a value. Their reasoning
is the same one this repository applies to a routing decision: stderr can quote
what was handed to it, so the only half safe to store is the half the program
wrote itself.

They asked (`iriguchi-work/05_sora_errors_requirement.md`) for a catalogue of
those names, modelled explicitly on `rules --json`, and separately — *as a
request, not a requirement* — for the first line to start with the kind.

Three things were measured before anything was written. Two were wrong here.

### The fold key was the program name

Every `IriguchiError` reached stderr as `iriguchi: <message>`:

    iriguchi: the scanner 'mamori' is registered and cannot be used ...
    iriguchi: --findings could not read '/nope/nothing.json' ...
    iriguchi: --findings is not a UTF-8 JSON document ...
    iriguchi: ['IRIGUCHI_LOCAL_URL', 'IRIGUCHI_LOCAL_MODEL'] is not set ...

`iriguchi` is a well-formed name and would have been accepted silently. Four
unrelated failures folding into one row carries the same information as a
counter. **The half filed as a request was the more urgent one.**

### The exit code said the opposite of what happened

iriguchi publishes `0` decided, `2` refused, `1` broken. Sora maps `2` to
`refused` and deliberately does not colour it as an error, because a refusal is
a decision this router stands behind.

argparse exits `2` for a mistyped flag. So:

    iriguchi --nosuchflag route "..."

reached a person as **your prompt was refused** — with no decision document
anywhere, because no decision had been made. A false statement about a policy
decision, produced by a typo. The README's own sentence had said which code this
should be since before the collision existed.

### The routing family is not a failure at all

`ScanError`, `EstimationError` and `JudgementError` are raised and never
printed. ADR-0002 turns each into the most restrictive route available with a
reason naming what broke, so they arrive as decisions. A catalogue listing only
what is printed would tell a consumer that a broken scanner produces nothing.

## Decision

**`iriguchi errors` publishes `iriguchi.errors/1-draft`, stderr's first line
begins with the kind, and a usage error exits `1`.**

Three things follow from that, and each is a decision rather than a detail.

**The message is named `ConfigurationError`, not a new kind.** A bad flag is *a
setting that was missing, malformed, or not recognised*, which is what that
exception already means. It is printed before the usage block, so the name is
first on stderr where Sora needs it and the error is above the usage text where
a person reads it.

**`retryable` means *may a consumer try this again*, not *would it work*.** The
two readings come apart on `RestorationError`: a second `ask` might well
succeed, and it would put the prompt through the outbound path a second time. A
router does not hand a consumer a reason to re-send a prompt, so the field
carries the narrower reading and the catalogue says so. `ModelError` is the only
`true`.

**The document has a third list.** `not_a_failure` names the routing family and
the rule identifier each becomes — resolvable in `rules --json`, and driven
through it by a test, because the first draft of the table pointed at
`routing.judge-failed` and there is no such rule. A broken judge is reported as
`cascade.judge-failed`, on the cascade's prefix, because the cascade is where it
changes anything.

## Consequences

**A consumer can check its own manifest against iriguchi's declaration** rather
than against a document somebody wrote once. That was Sora's stated reason for
wanting `exit_code` in the catalogue, and it is the reason a test drives each
declared code through the CLI rather than asserting it.

**The exit code change is visible to anything scripting iriguchi.** A script
that treated `2` as *refused* was being lied to by usage errors and is now told
the truth; a script that treated `2` as *any failure* now sees `1` for the
argparse half. The second is the smaller population and the first is the one the
README documented.

**`open_namespaces` is empty, and that is a claim.** Every kind is one of
iriguchi's own class names, because an adapter that catches a foreign exception
wraps it before the top-level handler can see it. The one that escaped —
`OSError` from an unreadable `--findings` file — was found by running the
command and is wrapped now. If a foreign exception ever surfaces, this field is
where it has to be declared, and the completeness test is what would force the
question.

**Nothing streams.** Sora asked for no stream, no callback, no socket, no
severity, and no shared family-wide error enum — a common enum is a shared
library with a different name, and the charter forbids it. Each sibling names
its own failures and Sora translates. This decision does exactly that and no
more.

**It is a draft.** It freezes when a second program both produces and consumes
it — a program that used it and found something, not a validator that accepted
it. Sora is the consumer; there is no second producer.
