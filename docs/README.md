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

## Where the project is right now

**Nothing is built.** The repository holds the design
([`proposals/0001-the-design.md`](proposals/0001-the-design.md)), the ten
decisions that design rests on ([`adr/`](adr/)), and the measurements that
forced two of them ([`measurements.md`](measurements.md)).

v0.1 is the router, headless: a domain, six ports, a deliberately over-detecting
fallback scanner, a rules complexity estimator, a CLI, and an evaluation corpus
that scores it. No GUI, no network, no model. The proposal's section 8 has the
rest.
