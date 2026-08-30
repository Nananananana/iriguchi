# 10. The layering is a test

**Status:** accepted

## Context

Every document in this repository says the domain imports nothing but the
standard library, that dependencies point inwards, and that the network lives in
one place. Written down, those are conventions, upheld by whoever last read
`AGENTS.md`. Conventions about imports lose to autocomplete.

They also decay silently. A layering diagram that no longer matches the code does
not fail; it just becomes fiction, and the next reader trusts it.

mamori's ADR-0017 is the record of deciding this once. tsumugi added
`import-linter` on top of the AST test, because the two catch different things.

## Decision

Both, and they are complementary.

**`tests/test_architecture.py`** walks every module with `ast` and asserts the
layer table module by module. It is the only thing that can express
*"`domain/` may import the standard library and nothing else"*, which is the
rule that matters most and which no import-linter contract type covers.

**`import-linter`** asserts five contracts in CI:

| Contract | What it stops |
|---|---|
| `layers` | an inward-pointing dependency reversing |
| `domain-purity` | the domain reaching down the stack |
| `domain-no-io` | the domain opening a file, a socket, a database or the argv |
| `no-network` | anything but a named adapter importing `socket`, `ssl`, `http`, `urllib`, `asyncio` |
| `mamori-is-an-adapter` / `tsumugi-is-json` | the sibling seams leaking inwards |

The `no-network` contract lists the permitted infrastructure packages one by one
rather than excluding the adapters. That is deliberate: a new adapter has to be
added to the list, which is the same maintenance obligation as the layer table
and the same reason for it.

`ALLOWED` in `tests/test_architecture.py` is the authority. `docs/architecture.md`
will describe it, and will be wrong rather than authoritative if the two ever
disagree.

## Consequences

A diagram that stops matching the code turns the build red instead of quietly
becoming fiction.

`no-network` is what makes "nothing left the machine" a test rather than a claim.
It is backed at runtime by a fixture that poisons `socket.socket` and asserts a
full `route --explain --dry-run` still completes — because the static contract
proves no *import*, and the fixture proves no *call*.

Any deliberate exception to the layer table is pinned to the exact file and
symbol it covers, so it cannot spread quietly into the rest of the layer. mamori
does this for its one default-construction exception, and the pinning is the part
that makes an exception survivable.

## What it costs

Two mechanisms to keep in step, and a contract file that has to be edited every
time a package is added. A developer who adds an adapter and forgets gets a
failure that names an import rather than a design problem, which reads as
bureaucratic until the first time it catches something.

It also forbids some genuinely convenient shortcuts — a domain helper that reads
an environment variable, a quick `urllib` call from the application layer — and
those refusals will occasionally cost an afternoon.
