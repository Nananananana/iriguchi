# 16. A decision can be published, because it holds no prompt

**Status:** accepted

## Context

[ADR-0012](0012-a-decision-inherits-the-classification-of-its-prompt.md) is
blunt: **a `RoutingDecision` is classified as highly as the prompt it describes,
is never written to disk, and is never sent.** There is no `--log-file` and that
is the point rather than an omission.

`iriguchi route --json` writes one to standard output, under a published,
frozen contract, for another program to read. That looks like the opposite of
ADR-0012 and needs an argument rather than a shrug.

The pressure to have it is real. iriguchi is the family's only repository that
**produces no contract at all** — every arrow in the family diagram points into
it and none comes out — and every 2026 command-line tool of this kind is
expected to have a machine-readable mode that pipes into `jq`. Neither of those
is a reason on its own; a privacy tool that grows a feature because tools have
that feature is how a privacy tool stops being one.

## Decision

**A decision may be published under `iriguchi.routing-decision/1`, and the
reason is what the document contains.**

    rule ids, source names, details   written by iriguchi, not by the prompt
    spans                            offsets into a prompt the reader lacks
    bands, scores, weights           arithmetic

**No string in the document is derived from the text.** A document saying
`fallback.email at 12-19` beside a prompt nobody has is not that prompt. What a
holder learns is that iriguchi's email rule matched seven characters somewhere,
which is what `route --explain` already prints to a terminal.

So ADR-0012 is unchanged in substance and one word sharper. It refuses to keep
**the decision object**, which carries the prompt's classification because it
was computed from the prompt. It never said that *nothing derived from a
decision may exist* — `route --explain` has printed the same content since v0.1,
and if printing it is safe then serialising it is safe by the same argument.

### What actually changed is who can be wrong about it

Printing to a terminal is read once by a person. A document under a contract is
read by programs, kept in files, and passed on. **So the constraint moves from a
habit to a check**: `tests/test_the_published_contract.py` plants values in
prompts and greps the emitted document for them, through the function and
through the command, and `tests/test_the_claims_with_no_mechanism.py` does the
same for every other command.

The schema states the invariant it cannot express, in its `$comment`, because a
consumer generating code from it needs to know that a span is an offset into
text they do not have and never will.

### What is refused

- **No prompt, no fragment of one, and no length.** A length is a fact about the
  text; the schema has no field for one and `additionalProperties: false` at
  every level means adding one is a contract change rather than a commit.
- **No file is written by iriguchi.** The document goes to standard output. A
  person who redirects it has chosen to keep it, which is different from a tool
  that decided for them, and it is the same line ADR-0012 drew.
- **Offsets are code points, not bytes.** An offset into UTF-8 bytes and an
  offset into characters disagree on every Japanese prompt, and a consumer that
  guesses wrong highlights the wrong words — silently, and worse the more the
  text needed protecting.

## Consequences

iriguchi becomes a producer. That is a role it has not had, and it comes with
the obligation the family has been finding the cost of all week: **a published
schema that nothing validates against is a promise with no check.** tsumugi's
reference loader accepted a package their own schema rejects; iriguchi's mamori
reader accepted eight of nine documents mamori's schema refuses. Every document
this can emit is validated against the shipped schema by a real JSON Schema
validator, in the test suite, before either half can drift.

`jsonschema` is a development dependency for that, and `cosmic-ray` was refused
three hours earlier for adding 726 lines to `uv.lock`. The difference is not
size — this adds 154 — it is that one was a convenience two hundred lines of
standard library replaced and the other is **an obligation to somebody
downstream**. `pip install iriguchi` still pulls nothing, and the wheel job that
proves it is unchanged.

## What it costs

**A frozen contract is a thing that cannot be improved.** v1 is closed the
moment somebody depends on it, and every field this schema does not have is a
field iriguchi cannot add without a v2 — including ones a consumer will
reasonably ask for, like a prompt hash or a timestamp.

Both of those are refused deliberately and neither is obviously right forever. A
hash of the prompt would let a consumer correlate two decisions about the same
text, which is useful for a cache and is also an oracle: somebody holding a
guess can confirm it. A timestamp turns a decision into a record of when
somebody was working. **The v1 answer to both is no, and the reason is written
here so that a v2 saying yes has to argue with it rather than around it.**
