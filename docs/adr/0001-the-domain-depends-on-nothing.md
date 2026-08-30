# 1. The domain depends on nothing, and does no I/O

**Status:** accepted

## Context

iriguchi sees every prompt a person types, before anything else does. That is a
more privileged position than any of its siblings occupy: mamori sees the text
you asked it to protect, tsumugi sees the folder you pointed it at, and iriguchi
sees all of it, including the prompts a person types and then deletes.

A runtime dependency in that position is code with unsupervised read access to
everything. Not because its author intends harm, but because a transitive
dependency six levels down is nobody's code in particular, and the audit surface
is the union.

Separately: the routing decision is the only security-relevant thing this
project does. It has to be testable with no model, no network, no filesystem and
no clock, because a decision that can only be tested by running the world is a
decision nobody re-tests after they change it.

## Decision

`domain/` imports the standard library and nothing else. Not pydantic, not an
LLM SDK, not `mamori`.

It also does no I/O. `domain/` may not import `os`, `pathlib`, `sqlite3`,
`tomllib`, `argparse`, `subprocess`, `socket`, `ssl`, `http` or `urllib`. Time
arrives through a `Clock` port when it is needed at all.

The package as a whole declares **zero runtime dependencies**, and CI checks it
by installing the wheel with no extras into a clean environment and asserting
nothing came along.

## Consequences

Every routing decision is a pure function of values. A test constructs a
`Sensitivity`, a `Complexity` and a `RoutingPolicy`, and asserts a `Route`. No
fixtures, no temporary directories, no mocking a network.

A domain that cannot open a file cannot be given a different answer by whatever
wrote the file. That closes a class of attack — configuration that changes a
routing verdict at read time — by construction rather than by review.

Enforced two ways: `tests/test_architecture.py` walks the `ast`, and
`import-linter`'s `domain-purity` and `domain-no-io` contracts assert it in CI.
The AST test is necessary because import-linter cannot express "everything
except the standard library".

## What it costs

Convenient things become inconvenient. Configuration has to be read at the edge
and passed in. Anything that wants the current time has to be handed a clock.
Some duplication with mamori's and tsumugi's own domain vocabulary is accepted
rather than shared, because sharing it would mean depending on them.

It also means iriguchi's built-in detection is worse than mamori's, permanently.
That is addressed in [ADR-0005](0005-detection-is-a-port.md) rather than solved
here.
