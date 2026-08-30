# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The design: `docs/proposals/0001-the-design.md`, written before any code
  exists and kept that way.
- Ten architecture decision records, `docs/adr/0001` through `0010`.
- `docs/measurements.md` and the two probes in `tools/`, which measured the
  original specification's performance invariants and found neither reachable.
- Project scaffold: Python 3.12, Apache-2.0, zero runtime dependencies, `ruff`,
  `mypy --strict`, six `import-linter` contracts, `pre-commit`, and a CI matrix
  over Linux and Windows that additionally asserts the wheel installs with
  nothing alongside it.
- The domain layer: `Span`, `Destination` and `Route`, `Finding` and
  `Sensitivity`, `Signal` and `Complexity`, `Reason` and `Removal`,
  `RoutingDecision`, and `RoutingPolicy` — the only place a route is chosen.
  Pure, stdlib only, no I/O, 100% covered, with the leak-impossibility invariant
  fuzzed by hypothesis rather than only exampled.
- `tests/test_architecture.py`: the layer table, walked with `ast` and asserted
  module by module — including the rule no import contract can express, that the
  domain may import the standard library and nothing else.
- `tests/conftest.py`: the network, poisoned for the whole suite. The import
  contracts prove nothing imports a socket; this proves nothing calls one.
- `ports/`: `SensitivityScanner` and `ComplexityEstimator`, with conformance
  suites in `tests/contracts.py` that an adapter inherits by subclassing.
- ADR-0011: a port arrives with its adapter. The design names six; two have
  both halves in v0.1, and the rest wait for the version that implements them.
- `infrastructure/normalization.py`: NFKC folding that keeps a map back to the
  original offsets, so a scanner can match `ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ`
  and still report spans into the text as given.
- `infrastructure/scanners/`: the built-in fallback scanner and the entropy
  rule behind one of its findings. Eight rules, each documenting which way it
  leans and what it also fires on; thresholds measured rather than chosen.
- `infrastructure/estimators/rules.py`: the complexity estimator. Nine rules
  across the two feature families it is allowed to use, three of them
  escalating, and a docstring that states plainly why this axis is the weaker
  of the two.
- `application/routing.py`: `PromptRouter`, which asks both proposers and then
  the policy. A proposer that fails produces a decision anyway — the most
  restrictive one available — with a reason naming what broke.
- `evaluation/`: the corpus (155 cases), its loader, and the scorer. Six
  figures, one of them a gate. `tools/generate_cases.py` plants the
  adversaries deterministically; `tools/borrow_mamori_cases.py` converts
  mamori's labelled samples once, offline, into a committed fixture.
- The credential rule now accepts `は` and `が` as separators, and requires the
  captured value not to begin with kana or kanji. The corpus found both halves.
- `config.py` and `interfaces/cli/`: the command line — `route`, `config`,
  `doctor`, `demo`, `eval` — and the `iriguchi` console script.
  `route --explain --dry-run` is the one the project is named after: it says
  where a prompt would go and which rules decided, and opens no socket.
- `policy.prefer-local` no longer claims a `HIGH` band "does not call for the
  larger model" when the external destination was removed. The CLI found it.
- `infrastructure/scanners/mamori_scanner.py`: mamori as a `SensitivityScanner`,
  opt-in via `--scanner mamori`, optional at runtime. It closes the fallback's
  largest gaps — a name with no honorific, an English name, a company — and
  carries no preview, confidence or detector name into a `Finding`.
- ADR-0012: a decision inherits the classification of the prompt it describes,
  amended once — the prohibitions were borrowed from mamori's ADR-0032 and were
  incomplete here, because a rule id names a topic and mamori's records never
  describe what a document is for.
- `mamori_state()` replaces a boolean that conflated "mamori is absent" with
  "mamori is installed and will not import". The seam test suite now skips on
  the first and fails on the second; `config`, `doctor` and the constructor no
  longer tell somebody with a broken install to install what they have.
- `docs/measurements.md`: what installing mamori buys, what that measurement
  does not say, and what iriguchi is *not* measured against (RouterBench and
  LLMRouterBench measure cost against quality; this measures whether
  sensitivity removes a destination).

The first release will be `0.1.0`.
