# 5. Detection is a port, mamori is its adapter, and the fallback errs toward local

**Status:** accepted

## Context

The original specification describes iriguchi detecting password-shaped strings,
particular organisation names and confidential keywords — a regex set, inside
iriguchi.

mamori is at 0.24.0. It has language packs for Japanese, English and Chinese, a
labelled evaluation corpus, a measured leaked-character rate, a documented list
of its own blind spots, and thirty-one ADRs of accumulated reasoning about
precisely this problem — including the ones that are not obvious until you have
been wrong once, like why `\b` never fires next to kanji and why a wide rule
needs a stated cost.

A fresh regex set inside iriguchi would be a worse mamori that nobody measures.

But iriguchi cannot *require* mamori either. It would stop being a library
someone can install and read in an afternoon, and it would mean a person who
wants only a router has to take a whole privacy layer to get one.

## Decision

`SensitivityScanner` is a port. Text in, findings out.

**mamori is an adapter**, in `infrastructure/` and nowhere else. `domain/`,
`ports/`, `application/`, `interfaces/` and `evaluation/` may not name it, and
`import-linter`'s `mamori-is-an-adapter` contract asserts that. It is an optional
extra (`pip install iriguchi[siblings]`), and the integration tests skip when it
is absent.

**iriguchi ships a built-in fallback scanner, and it is deliberately dumb.** A
short, readable set of shape rules: a run of digits, an `@`, a key-shaped token,
a `-----BEGIN`. It is permitted to be wrong in exactly one direction — it
over-detects, so it over-routes to local, which is
[ADR-0002](0002-fail-closed.md)'s safe error.

**Precision is what mamori buys.** The fallback decides what must stay local;
mamori is what lets a prompt the fallback flagged actually leave, because mamori
can tell an order number from a My Number and the fallback cannot.

## Consequences

iriguchi works standalone, conservatively. It works well with mamori installed.
Neither configuration can leak more than the other, because the direction of the
fallback's error is toward the safe route.

The scanner port gets a conformance suite in `tests/contracts.py`, the way
mamori does it for `Detector` and `MappingStore`. An adapter subclasses the
mixin and inherits the contract.

When the escalation path is built (v0.2), it points at **mamori's proxy**, not
at an upstream API. iriguchi never sends raw text anywhere: the protection and
the restoration are mamori's job, and a test asserts iriguchi has no code path
that reaches an upstream directly.

## What it costs

Standalone iriguchi over-routes, and the over-caution rate is a real number the
evaluation report has to publish rather than hide. Some people will find the
fallback annoying enough to install mamori, which is the intended pressure, and
some will find it annoying enough to stop using iriguchi, which is the price.

Two scanners also means two sets of behaviour to explain. `--explain` has to say
*which* scanner produced a finding, or the person cannot tell an over-detection
from a real one.
