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

Nothing is implemented. The first release will be `0.1.0`.
