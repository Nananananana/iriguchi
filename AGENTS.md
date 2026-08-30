# AGENTS.md

Context for AI assistants (and future humans) working on iriguchi. Read this
whole file before proposing or writing any change.

This file is current state and current rules. It is not a history: why a thing is
the way it is lives in `docs/adr/`, and what might happen next lives in
`docs/proposals/`. `docs/README.md` explains that separation and why it matters.
**A statement here that disagrees with the code is a defect.**

## What iriguchi is

A local governance router. It stands between a person and every model they use,
and decides — locally, deterministically, before a single byte leaves the
machine — where each prompt is allowed to go: `LOCAL`, `EXTERNAL` (via mamori),
or `REFUSED`.

The three siblings each own one question. mamori: *what in this text is
sensitive?* tsumugi: *what evidence bears on this question?* akashi: *did the
answer stay inside its evidence?* iriguchi owns the fourth, which none of them
asks: **where is this prompt allowed to go, and who decided?**

That framing says what iriguchi must *not* build. It must not grow a second,
worse PII detector. It must not grow a second context builder. It is the water
gate, not the reservoir.

The constitution, to be enforced by construction rather than by promise:

- **Sensitivity is a veto; complexity is a preference.** They are never one
  score, and no arithmetic exists between them anywhere in the codebase. A
  sufficiently hard prompt cannot out-vote a finding (ADR-0003).
- **Fail closed.** Doubt routes local. Must-stay-local with no local model
  available is `REFUSED`, never a fall-through to the network (ADR-0002).
- **The decision is made before the request, from query features, by rules.** No
  model call, no learned weights, no network in the deciding path (ADR-0004).
- **The deciding path has no way to send.** Not by discipline — by an import
  contract and a poisoned `socket.socket` in a test (ADR-0010).
- **Say why, and say why not.** Every decision carries the rules that fired and
  the destinations that were removed, with their reasons. A `Reason` names a
  rule id and a span, and never the matched value (ADR-0006).
- **The domain depends on nothing and does no I/O.** Not even `os` or `pathlib`.
  A domain that can open a file can be given a different answer by whatever
  wrote the file (ADR-0001).
- **Detection is a port.** mamori is its adapter; the built-in fallback is
  deliberately dumb and errs toward local (ADR-0005).
- **A number is measured, or it is not written** — with its residual, meaning
  what the measurement does not say (ADR-0008).

## Architecture map

There is no `docs/architecture.md` yet, deliberately: an ADR before the code is
legitimate, a current-state document before the code is fiction. The intended
shape is `docs/proposals/0001-the-design.md`, section 4.

```text
interfaces --> application --> domain
                   |              ^
                   |              |
                   +--> ports <---+-- infrastructure
```

| Layer | May import |
|---|---|
| `domain/` | **stdlib only** — and no `os`, `pathlib`, `socket`, `argparse`, `tkinter`; never `mamori` or `tsumugi` |
| `errors.py` | nothing |
| `ports/` | `domain`, `errors` |
| `application/` | `domain`, `ports`, `errors` |
| `infrastructure/` | `domain`, `ports`, `errors` |
| `evaluation/` | `domain`, `ports`, `application`, `infrastructure` |
| `config.py` | everything above |
| `interfaces/` | everything above |

This table is executable: `tests/test_architecture.py` parses every module and
asserts it, and `import-linter` asserts the direction across six contracts. A
diagram that stops matching the code turns the build red rather than quietly
becoming fiction.

The `no-network` contract is the one that carries the project's central promise.
It lists the permitted infrastructure packages one by one rather than excluding
the adapters, so a new adapter has to be added to the list.

## Conventions

Taken from `kiseki`, `mamori` and `tsumugi`, which paid for them.

- **Everything in the repository is English.** Conversation language may differ;
  committed text may not.
- TDD. One issue, one PR, squash merge, close the issue after.
- **All tests must pass before any commit.** One failure means stop and
  investigate, not proceed.
- Test file names are unique across the repository — tests are not a package and
  duplicate basenames break collection.
- Any test that invokes the CLI isolates itself: chdir to `tmp_path` and strip
  `IRIGUCHI_*`. A CLI test that writes into a developer's real configuration is
  a bug waiting in every future test file.
- Checks before every green commit: `uv run pytest -q`, `uv run mypy src`,
  `uv run lint-imports`, `uv run ruff check --fix .`, `uv run ruff format .`,
  `uv run pre-commit run --all-files`. If pre-commit rewrites anything,
  `git add` and run it again — a commit whose hooks failed did not happen.
- Windows: set `PYTHONUTF8=1`. This project reads Japanese text in every test.
- Tests that call a real model carry the `llm` marker and are excluded from CI
  by default (`addopts = -m 'not llm'`); run `uv run pytest -m llm` before
  merging model-adjacent changes.
- Read-only dumps for an assistant go **outside** the working tree.

## Rules particular to this project

- **Never write an architecture document for code that does not exist.** ADRs
  before code are legitimate; a current-state document before code is fiction.
- **A rule without an id is not a rule.** An id is what lets somebody disable it
  without forking the library, and what lets a `Reason` name it.
- **A `Reason` carries a rule id and a span. Never the matched value.** A router
  that logs the thing it was protecting has undone itself.
- **Anything that changes routing is gated on `iriguchi eval`.** Run it before
  and after.
- **Floors, not targets.** The eval gate is deliberately looser than the current
  scores. A gate set at today's number makes every honest experiment a build
  failure, and tuning to reach a threshold is what mamori's ADR-0023 records.
  The one exception is **leak rate, whose floor is zero.**
- **Every discarding path carries its reason to the end.** A decision returns a
  narrower set of destinations *and* an account of what it removed. This is
  invasive to retrofit, so it is done from the first decision.
- **Ordering discipline.** No unordered iteration reaching an output, no partial
  sort keys, no wall-clock in a decision. The same prompt decided twice must
  produce byte-identical output, and a property test asserts it.
- The `mamori` integration tests are worth their setup cost: the interesting
  failures are at the seams, and the seams only exist when something real is on
  both sides.
- Working notes, review history and experiments are kept **outside this
  repository** and are not published.

## Current state

- Version `0.1.0.dev0`. **Nothing is implemented.** The repository holds the
  design, ten ADRs, the measurements, and the project scaffold.
- **License: Apache-2.0. Python: 3.12+. Runtime dependencies: 0**, checked in CI
  by installing without extras and asserting nothing came along.
- **Next, per `docs/proposals/0001-the-design.md` section 8:** v0.1 is the
  router, headless — `domain/` (`Route`, `Sensitivity`, `Complexity`, `Reason`,
  `RoutingDecision`, `RoutingPolicy`), six ports with conformance suites, the
  over-detecting fallback scanner, the rules complexity estimator, the CLI
  (`route`, `explain`, `config`, `doctor`, `eval`, `demo`), and the evaluation
  corpus with `tools/generate_cases.py`.
- **v0.1 exit criterion:** on the corpus, leak rate is zero and route accuracy is
  measured and written down; a test proves no socket opens on any local route;
  the wheel installs with zero runtime dependencies.
- **Not built, and deliberately so:** the cascade. Answering locally, judging the
  answer weak and escalating is a real technique, but it re-sends text that was
  already judged, so it needs the domain to say the escalation is permitted
  *again*. Deferred to v0.3; the domain gets room for it, not the behaviour.
- The evaluation corpus borrows labels from mamori's
  `evaluation/data/*-core.json` — every value there is invented and already
  curated. A sample with an entity is `MUST_STAY_LOCAL`; a negative sample is
  `MAY_LEAVE`. The traps are what the generator adds on top (ADR-0007).
