# 9. tsumugi is read as JSON, and never imported

**Status:** accepted

## Context

The Anchor Dashboard renders provenance: which document, which offset, which
hash a model's context came from. That data is tsumugi's `ContextPackage`, whose
contract is frozen at version `1` and published as
`schemas/context-package-1.json` — `contract`, `query`, `items`, `omissions`,
`budget`, `provenance`, all required.

The obvious implementation imports tsumugi and reads the dataclasses.

kiseki already decided this the other way, for a reason that generalises: its
adapter imports nothing, because the export is a published JSON contract, and a
test asserts no import creeps in.

## Decision

iriguchi never imports tsumugi. Not in `domain/`, not in `application/`, not in
`infrastructure/`. `import-linter`'s `tsumugi-is-json` contract has
`iriguchi` as its whole source and `tsumugi` as its whole forbidden set.

The dashboard reads a JSON document, validates `contract`, and refuses an
unrecognised version rather than guessing at it —
[ADR-0002](0002-fail-closed.md) applies to contracts as much as to prompts.

The same applies to akashi's audit output when it arrives.

## Consequences

iriguchi renders a package produced by any version of tsumugi that speaks
contract 1, including one running in a different process, a different
virtualenv, or on a different machine. It renders a package produced by
something that is not tsumugi at all, which is what a published contract is
*for*.

There is no version coupling to manage, no shared dataclass to keep in step, and
no reason for tsumugi's release cadence to constrain iriguchi's.

`omissions[]` is rendered as prominently as `items[]`. tsumugi's ADR-0005 exists
because a silent truncation reads as completeness, and a dashboard that shows
what was found while hiding what was left out reintroduces exactly the problem
that field was added to solve.

## What it costs

Reading JSON by hand instead of getting typed objects for free. Field names
appear as string literals in iriguchi's reader, and a contract-conformance test
against the published schema is the only thing keeping them honest — so that
test is not optional.

If tsumugi ever ships contract 2, iriguchi finds out by refusing a package,
rather than by failing to import. That is the intended failure, and it is louder
than the alternative.
