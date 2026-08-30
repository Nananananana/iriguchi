# The documents, and what each one is for

iriguchi's documentation is written so that three different things never get
mistaken for one another:

- **what is true now** — the current architecture and rules;
- **why it became true** — the decisions, as they were made;
- **what might become true** — proposed and planned work.

A reader who cannot tell these apart will implement a proposal as though it
shipped, or "fix" an ADR to match today's code and erase the reasoning that
produced it. Both have a cost that grows with the project, so the separation is
structural: each document says at the top which of the three it is.

This convention is taken from the sibling `kiseki` and `tsumugi` projects, which
learned it the expensive way.

## Responsibilities

| Document | Responsibility |
|---|---|
| `README.md` | For anyone outside: what iriguchi is, what it solves, what it can do |
| `AGENTS.md` | For contributors and AI agents: the current rules, constraints and state |
| `docs/adr/` | Decisions as they were made, with their reasons — history |
| `docs/proposals/` | Proposed or planned work — not necessarily implemented |
| `docs/measurements.md` | What things actually cost on real hardware, with the tools that produced them |
| `docs/architecture.md` | The current architecture — **not yet written, because there is not yet an architecture to describe** |
| `CHANGELOG.md` | The released history, briefly |

## The rules that keep them apart

- An ADR is not edited to match the present. A decision that no longer holds is
  superseded by a later ADR that says so; the original stays as it was written,
  because the reasoning is the point.
- A proposal is never cited as evidence that something exists. When a proposal
  lands, the current-state documents change and the proposal stays where it is,
  describing what was proposed.
- The current-state documents describe what the code does today. If one of them
  disagrees with the code, one of the two is wrong and the disagreement is a
  defect — not a difference of opinion.
- An architecture document says why, not only what. A rule without its reason is
  a rule the next reader will break for good reasons of their own.
- **A number in a document is measured, or it is not written** — and it ships
  with its residual, meaning what the measurement does *not* say.
- **A residual lives attached to what it qualifies, never in a file of its own.**
  Every ADR has a *What it costs* section, `measurements.md` has *What these
  numbers do not say*, and a limit on a value object goes in its docstring. A
  `docs/concerns/` was considered and declined: a concern filed away from the
  claim it bounds is a concern the person reading the claim does not see, and the
  claim is where the reading happens. The cost of that choice is that a concern
  spanning several documents has no single home and gets written in each — which
  is duplication, and is cheaper than the alternative.

## Where the project is right now

**v0.1 is built, and it is headless.** A prompt goes in, a decision comes out,
and the whole of it runs with no GUI, no network and no model:

- `domain/` — the routing values and the policy, the only place a route is chosen
- `ports/` — two protocols, with conformance suites their adapters inherit
- `infrastructure/` — the deliberately-dumb fallback scanner and the rules estimator
- `application/` — the use case that asks both proposers and then the policy
- `evaluation/` — 155 labelled cases and the report that scores them
- `interfaces/cli/` — `route`, `config`, `doctor`, `demo`, `eval`

**Not built:** everything with a seam or a surface. mamori as a scanner and as an
escalation channel, ollama as a local model, `iriguchi ask` (v0.2); the tray and
the popup (v0.3); the Anchor Dashboard (v0.4). The proposal's section 8 has the
order and the reasons.

`architecture.md` is still absent, and now for a different reason than before:
there is an architecture, and `AGENTS.md` describes it, and the layer table there
is asserted by `tests/test_architecture.py`. A second document saying the same
thing is a second document to keep in step. It arrives when there is something
`AGENTS.md` cannot hold.
