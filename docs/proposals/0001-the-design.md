# iriguchi — the design, and the road to v1.0

**Status: proposal.** This is the design as it was written before any code
existed, and it stays that way — it is never edited to match what was
eventually built, and it is never evidence that anything exists. What is
*decided* lives in [`docs/adr/`](../adr/); what is *true* will live in
`docs/architecture.md`, which is not written until there is an architecture to
describe. See [`docs/README.md`](../README.md) for why those three are kept
apart.

Written against the original specification (v0.1.0 draft, held outside this
repository). This revises it in three places — section 3 — and adopts the rest.

---

## 1. What iriguchi is

A local governance router. It stands between a person and every model they use,
and decides — locally, deterministically, before a single byte leaves the
machine — where each prompt is allowed to go.

Three destinations:

```text
                    a prompt
                        |
              +---------v---------+
              |     iriguchi      |   sensitivity gate, then complexity
              +---------+---------+
        +---------------+---------------+
        v               v               v
    REFUSED        LOCAL SLM       ESCALATED
   nothing runs   ollama, on      via mamori, protected,
                  this machine    restored on the way back
```

The three sibling projects each own one question. mamori: *what in this text is
sensitive?* tsumugi: *what evidence bears on this question?* akashi: *did the
answer stay inside its evidence?* iriguchi owns the fourth, which none of them
asks: **where is this prompt allowed to go, and who decided?**

That framing matters because it says what iriguchi must *not* build. It must not
grow a second, worse PII detector. It must not grow a second context builder. It
is the water gate, not the reservoir.

## 2. What is adopted from the specification, unchanged

- **Two-axis routing.** Sensitivity and difficulty are evaluated separately,
  before the request, by deterministic code. This is the right shape, and the
  literature agrees with it (section 5).
- **Fail closed.** Doubt routes local. Doubt with no local model available
  refuses. Never "when unsure, send it".
- **Zero runtime dependencies, clean architecture, the domain on the standard
  library alone.** The same constitution as mamori, tsumugi and kiseki.
- **The Anchor Dashboard.** Reading tsumugi's `ContextPackage` and akashi's
  audit output and showing a person which file, which offset, which hash. This
  is the reason a UI exists at all.
- **Minimalism as a stance.** Electron is genuinely the wrong answer for a
  process that is resident all day.

## 3. What is revised, and why

### 3.1 The performance invariants were not measured. They are now.

The specification asks for **10 MB resident** and **1 ms startup**. Measured on
the development machine ([`docs/measurements.md`](../measurements.md)):

| | Specification | Measured floor |
|---|---|---|
| Resident memory | 10 MB or less | **12.8-14.2 MB** bare interpreter, **27.0-28.8 MB** with a Tk window |
| Startup | 1 ms or less | **32 ms** bare interpreter at best, **135 ms** to a realised Tk window at best |

Neither is a slow implementation of the design. The interpreter is 12.8 MB
before any of our code loads, and process creation is 32 ms before it starts.
Writing less code does not reach either number.

The startup figure is also unstable: the same operation on the same interpreter
measured 32 ms once and a 796 ms median an hour later, because process creation
on Windows is dominated by the filesystem cache and the antivirus scanner. The
memory figure moves by at most 0.4 MB. That difference is what decides which of
the two becomes an invariant.

**The revision:** keep the stance, replace the numbers, and change which number
is the invariant. What a person actually experiences is not cold start — a
resident tray process pays that once, at login — it is the *warm* path: hotkey
pressed, input box visible. That is the number worth gating a build on, and it
is measurable in the tens of milliseconds.

Proposed floors, to be set from a real measurement at v0.3 rather than now:

- **Warm popup latency** — hotkey to visible, on a resident process. The
  headline invariant.
- **Routing decision latency** — prompt in, decision out, no model. Should be
  sub-millisecond for ordinary prompts, and is gated from v0.1.
- **Idle resident memory** — a ceiling chosen from the measured baseline plus a
  stated headroom, not from a round number that sounded impressive.

A floor set at today's number makes every honest experiment a build failure —
tsumugi's rule, and mamori's ADR-0023 is the record of what happens without it.
So: floors well above the measurement, ratcheted down when they are earned.

### 3.2 v0.1 is the router, not the tray.

The specification's v0.1 leads with system-tray residency and treats the routing
engine as an MVP alongside it. This inverts that.

The tray cannot be evaluated. There is no corpus of correct tray behaviour, no
labelled dataset, no regression a test can catch. The router can be evaluated,
and it is the part that carries every security consequence in the project. Every
sibling project built the deterministic core first and measured it before
anything with a surface. That is not a coincidence; it is the only order in
which the hard part gets tested.

So **v0.1 is headless**: a library, a CLI, an evaluation corpus, and a number.
The GUI is v0.3, and it arrives after the thing it is a window onto is known to
work.

### 3.3 Detection is a port, and mamori is its adapter.

The specification describes iriguchi's privacy classifier as detecting
password-shaped strings, particular organisation names and confidential
keywords. mamori is at 0.24.0, has a measured detection corpus in three
languages, thirty-one ADRs of accumulated reasoning about exactly this, and a
documented list of its own blind spots. A fresh regex set inside iriguchi would
be a worse mamori that nobody measures.

**The revision:** `SensitivityScanner` is a port. mamori is the adapter that
implements it well. iriguchi ships a deliberately dumb built-in fallback, and
the fallback is allowed to be wrong in exactly one direction — it over-detects,
so it over-routes to local, which is the safe error. The precision that lets a
prompt *leave* the machine is bought by mamori being present.

This keeps the sibling rule tsumugi already enforces: `domain/` never imports
mamori; only an adapter may, and an architecture test asserts it.

## 4. Architecture

```text
interfaces --> application --> domain
                   |              ^
                   |              |
                   +--> ports <---+-- infrastructure
```

| Layer | Holds | May import |
|---|---|---|
| `domain/` | `Route`, `Sensitivity`, `Complexity`, `RoutingDecision`, `Reason`, the policy that combines them, layout arithmetic | **stdlib only**, and not `os`, `pathlib`, `socket`, `tkinter` |
| `errors.py` | the exception tree | nothing |
| `ports/` | `SensitivityScanner`, `ComplexityEstimator`, `LocalModel`, `EscalationChannel`, `ProvenanceSource`, `Clock` | `domain`, `errors` |
| `application/` | `route_prompt`, `answer_locally`, `escalate`, `render_view` | `domain`, `ports`, `errors` |
| `infrastructure/` | the rules scanner, the mamori adapter, the ollama adapter, the ContextPackage reader, the Tk adapter | `domain`, `ports`, `errors` |
| `evaluation/` | the corpus, the scorer, the report | `domain`, `ports`, `application`, `infrastructure` |
| `config.py` | every switch | everything above |
| `interfaces/` | the CLI, then the GUI | everything above |

Enforced two ways, as tsumugi does it: `tests/test_architecture.py` walks the
`ast` and asserts the table, and `import-linter` asserts the direction across
named contracts. The stdlib-only rule needs the AST test, because import-linter
cannot express "everything except the standard library".

Four contracts to write on day one:

1. **Layer direction.** The stack above.
2. **Domain purity.** `domain` reaches nothing below it, and imports no `os`,
   `pathlib`, `socket`, `argparse` or `tkinter`.
3. **The network lives in one place.** Only named adapter modules may import
   `socket`, `ssl`, `http` or `urllib`. This is the contract that makes
   "nothing left the machine" a test rather than a claim.
4. **Siblings are optional.** Only adapters may name `mamori`, and nothing may
   import `tsumugi` at all, because that seam is a published JSON contract and
   reading JSON is reading JSON. kiseki's adapter pattern, and a test asserts no
   import creeps in.

### Where the decisions live

Every routing decision is in `domain/`, and none of it is in a swappable
component. A scanner *proposes* sensitivity; an estimator *proposes* complexity;
the policy in `domain/` decides. A hallucinating local model, a broken regex, an
adapter that returns nonsense — none of them can turn a must-stay-local prompt
into an outbound request, because none of them holds the decision.

## 5. The routing algorithm, and where it comes from

The 2026 survey on dynamic routing and cascading frames the design space on three
axes: **when** the decision is made, **what** feeds it, and **how** it is
computed. iriguchi is pinned on all three, deliberately at the cheap end:

- **When:** before the request. Always. A decision made after a first response is
  a decision made after the text was already sent.
- **What:** query features only. No model call, no history, no learned weights in
  the deciding path.
- **How:** rules. Auditable by reading them.

That is a deliberate refusal of the accuracy the learned routers buy. The reason
is that this router's errors are not symmetric: a wrongly-cheap route costs
answer quality, and a wrongly-outbound route costs a leak that cannot be undone.
A router a person cannot read is a router they cannot trust with the second kind
of error.

**Two axes that are never collapsed into one score.**

*Sensitivity is a veto.* It removes destinations. It is never traded against cost
or quality, and no complexity score can restore a destination it removed. PRISM
(AAAI 2026) does the same thing in the same order — profile entity-level
sensitivity first, gate second — and 2026 hybrid-architecture practice is blunt
about the failure mode: a sensitive request that cannot be served locally must
return an error, not quietly go to the cloud.

*Complexity is a preference.* It chooses among whatever sensitivity left
standing. The features are the ones computable before any model runs, and the
literature's list is the starting set: length, language and script mix, code
markers, requested output shape, rare-word rate, and multi-step markers
(hikaku shite, shoumei shite, naze — against honyaku shite, youyaku shite).

**What is deliberately not built in v0.1:** a cascade. Answering locally, judging
the answer weak, and escalating is a real technique and the survey's third axis,
but it re-sends text that was already judged, so it needs the domain to say the
escalation is permitted *again*. The domain gets room for it; the behaviour waits
for v0.3.

## 6. Evaluation: what the corpus is, and what it cannot tell you

The corpus is the project. A router with no labelled cases is an opinion.

**Generated, deterministically, by `tools/generate_cases.py`.** No model, no
random seed — the same command produces byte-identical fixtures, so a regression
is a diff rather than a mystery. tsumugi's generator is the template, including
the oracle that checks each case is solvable and non-trivial before it is
written.

**Borrowed labels, which is the cheapest good decision available here.**
`mamori/src/mamori/evaluation/data/*-core.json` holds annotated Japanese,
English and Chinese samples, every value invented, already curated, already
argued over. Each sample carrying an entity is a **MUST-STAY-LOCAL** case; each
negative sample is a **MAY-LEAVE** case. That is a labelled sensitivity corpus
for the cost of a loader. tsumugi's cases supply prompts with known answers, and
those carry complexity labels.

**The traps are the dataset.** A corpus of obvious cases measures nothing,
because every router passes it. Per tsumugi's ADR-0013, each case plants one
correct route and at least one adversary:

| Trap | Shape |
|---|---|
| Looks sensitive, is not | a public documentation URL, a fictional character, a sample key from a vendor's own README |
| Looks trivial, is not safe | "translate this", followed by a paragraph containing an API key |
| Long and easy | a pasted log with "summarize this" — length is not difficulty |
| Short and hard | "prove this lemma" — four words, and no small model will do it |
| Mixed script | Japanese prose with an English code block |
| Sensitive outside the prose | the secret is in an attached tool-call payload, not the sentence — mamori's ADR-0030 found this one |
| Near-duplicate prompts, opposite routes | one character's difference flips the decision, and the reason must say which character |

**Scored without a model.** Exact route match against the label. RouterArena's
2026 finding is the reason: LLM-as-judge scoring deviated from exact match by up
to 10–24 points on knowledge tasks, which is larger than most routing gains
being claimed. CI calls no model, ever. `iriguchi eval --model NAME` is the
opt-in half that does, and its numbers are never a floor, because they are a
property of this code *and* whichever model was pulled.

**The report** takes RouterArena's dimensions, adapted: route accuracy, **leak
rate** (must-stay-local cases that were routed out — the only metric allowed a
floor of zero), over-caution rate (may-leave cases held back), optimal-selection
rate, and decision latency.

**The residual, stated:** the corpus is generated from templates, so it measures
whether the rules do what the rules intend, not whether real prompts look like
the templates. It cannot tell you the leak rate on a stranger's actual work.
Nothing in it substitutes for mamori's own detection numbers.

## 7. The tests the whole project is shaped around

Three shapes, and the third is the one that matters most.

**1. The prompt is a document, and it is asserted on.** Whatever iriguchi
composes — for the local model, or for the upstream request — is rendered and
compared against a golden file. No model runs. mamori's `prompts/` package and
`mamori prompt detection` are the pattern: the prompt is a value, addressable,
diffable, reviewable.

**2. It answers, and that path is marked.** The local-model path really calls
ollama, carries pytest's `llm` marker, and is deselected in CI. kiseki's rule:
run `pytest -m llm` before merging anything model-adjacent, and never let CI
depend on a model being pulled.

**3. It decides and sends nothing.** `iriguchi route --explain --dry-run` reads
a prompt, prints the destination and the reason, and opens no socket. The test
asserts the second half — not by trusting the code path, but by making the
attempt fail: the network contract from section 4, plus a fixture that poisons
`socket.socket` for the duration. This is the highest-value test in the project,
and it needs no model, no network and no GUI, which is why it can exist from the
first week.

Every routing decision carries its reason to the end. A decision is a
`RoutingDecision` holding a `Route`, the axes that produced it, and an ordered
list of `Reason`s naming which rule fired on which span. `--explain` prints them.
Retrofitting this is invasive, so it is built into the first decision the domain
ever makes — tsumugi's "every discarding path carries its reason" rule, applied
to a routing path.

## 8. Roadmap

### v0.1 — The router, headless

- `domain/`: `Route`, `Sensitivity`, `Complexity`, `Reason`, `RoutingDecision`,
  `RoutingPolicy`. Pure, stdlib only, no I/O.
- `ports/`: all six protocols, with contract test suites in `tests/contracts.py`
  the way mamori does it, so an adapter inherits its conformance suite.
- `infrastructure/`: the built-in fallback scanner (over-detecting, on purpose)
  and the rules complexity estimator.
- `interfaces/cli`: `route`, `explain`, `config`, `doctor`, `eval`, `demo`.
- `evaluation/`: the corpus, the loader that borrows mamori's samples, the
  scorer, `tools/generate_cases.py`.
- The four architecture contracts, green.
- **Exit criterion:** on the corpus, the leak rate is zero and route accuracy is
  measured and written down. A test proves no socket opens on any local route.
  Zero runtime dependencies, checked in CI by installing without extras.

### v0.1.1 — What the audit found

Added after [`docs/feasibility.md`](../feasibility.md), which re-read this design
against what it can be shown doing rather than against what it says. The three
items below are the ones that change what a user gets, in the order the audit
ranks them.

- **A corpus of requests.** The complexity axis decides **2 outcomes in 155**,
  and **0 of the 134 borrowed cases**, whose median length is 34 characters.
  They are a PII detector's samples and they were never requests for work, so
  the preference axis has nothing to read. Until prompts exist that can exercise
  it, iriguchi has one measured axis and one designed one, and the README says
  so. **The fix is prompts, not thresholds** -- `tools/calibrate.py --sweep`
  will produce any outward rate anybody wants and none of them is evidence.
  Measured by `tools/which_axis.py`; the published counts are recomputed on
  every test run.
- **A decision about the external half.** `ask --external` needs mamori to
  protect the outbound prompt, there is no unprotected fallback by construction,
  and **mamori is not on PyPI** -- so the destination is reachable by nobody who
  is not on the author's machine, and the remedy iriguchi prints names a
  relative path that only resolves there. Either mamori ships, or v0.1 states
  that the external route requires a sibling checkout and stops describing a
  door nobody can open. The second costs nothing and does not foreclose the
  first.
- **The scanner's advice has to become followable.** `missed findings` is 63.5%
  and the printed remedy is *install mamori*, which is the same unreachable
  package. The number is honest; the sentence after it is not actionable.

**Exit criterion:** the two axes are described in the README with the evidence
each of them has, and no command prints advice a user cannot act on.

### v0.2 — The seams

- The mamori adapter: `SensitivityScanner` backed by a real `PrivacySession`,
  and `EscalationChannel` pointed at mamori's OpenAI-compatible proxy rather
  than at an upstream directly. iriguchi never sends raw text anywhere, and a
  test asserts it.
  **Superseded by [ADR-0014](../adr/0014-ask-holds-its-own-upstream.md).** These
  two sentences contradict each other: through the proxy, iriguchi sends
  unprotected text to `127.0.0.1:8100` and mamori protects it there, so raw text
  crosses a socket. The channel protects in-process and keeps the promise the
  second sentence makes. Written here rather than corrected, because a proposal
  that quietly matches the code stops being evidence of what was decided when.
- The ollama adapter for the local model.
- `iriguchi ask` — the only command with an outbound path, named in an
  allow-list a test asserts, and it says where it is sending before it sends.
- `llm`-marked tests, deselected in CI.
- Integration tests against the real mamori, skipped when it is absent. The
  interesting failures are at the seams.

### v0.3 — The shell

- Tray residency, a global hotkey, a popup input. tkinter — and if tkinter
  cannot do it, that finding is an ADR rather than a dependency added quietly.
- `tests/test_performance.py` lands with **measured** floors: warm popup
  latency, decision latency, idle resident memory. Numbers chosen from a
  measurement of the real resident process, with headroom, ratcheted down as
  they are earned.
- The cascade: escalate a weak local answer, but only where the domain says the
  prompt was permitted to leave in the first place.

### v0.4 — The Anchor Dashboard

- A `ContextPackage` contract 1 reader — JSON, and no import of tsumugi.
- akashi's audit output alongside it.
- The evidence sidebar: which document, which offset, which hash, click to open.
- `omissions[]` rendered as prominently as `items[]`. A dashboard that shows
  what was found and hides what was left out reads as completeness.

### v1.0 — Offline, and no new intelligence

- Full-offline fallback routing: the network is gone, everything is local, and
  the person is told rather than left waiting.
- Documentation, the threat model, the published contracts frozen.
- v1.0 adds no new intelligence. kiseki's rule, and it is the right one.

## 9. How the work proceeds

Taken from kiseki and tsumugi, which paid for these.

- **Python 3.12, Apache-2.0, `uv`, hatchling.** Zero runtime dependencies,
  asserted in CI by installing without extras.
- **TDD.** One issue, one PR, squash merge, close the issue. The tests are the
  specification: write the failing test, make it pass, then tidy.
- **All tests pass before any commit.** One failure means stop and investigate.
- **Everything in the repository is English.** This conversation may be
  Japanese; committed text may not.
- Before every green commit: `uv run pytest -q`, `uv run mypy src`,
  `uv run lint-imports`, `uv run ruff check --fix .`, `uv run ruff format .`,
  `uv run pre-commit run --all-files`. If pre-commit rewrites anything,
  `git add` and run it again.
- Windows: `PYTHONUTF8=1`. This project handles Japanese text in every test.
- Test file names unique across the repository.
- Any CLI test isolates itself: chdir to `tmp_path`, strip `IRIGUCHI_*`.
- **Three kinds of document, never confused.** `docs/adr/` is why it became
  true, and is never edited to match the present; `docs/proposals/` is what
  might become true, and is never cited as evidence that something exists;
  `docs/architecture.md` is what is true now, and is not written until there is
  something to describe.
- **A number in a document is measured, or it is not written** — with its
  residual: what the measurement does not say.
- **Anything that changes routing is gated on `iriguchi eval`.** Run it before
  and after.
- **Floors, not targets.** The gate is looser than the current score. Tuning to
  reach a threshold is what mamori's ADR-0023 records.
- Working notes, reviews and experiments stay in `iriguchi-work/` and are never
  published.

### The ADRs to write before the first line of code

Decisions already made are legitimately recorded before the code exists.

| # | Decision |
|---|---|
| 0001 | The domain depends on nothing, and does no I/O |
| 0002 | Fail closed: doubt routes local, and local-impossible refuses |
| 0003 | Sensitivity is a veto, complexity is a preference, and they are never one score |
| 0004 | The decision is made before the request, from query features, by rules |
| 0005 | Detection is a port; mamori is its adapter; the fallback errs toward local |
| 0006 | Every decision carries its reasons to the end |
| 0007 | The evaluation corpus calls no model, and the traps are the dataset |
| 0008 | The performance invariants are the warm path, measured |
| 0009 | tsumugi is read as JSON and never imported |
| 0010 | The layering is a test |

## 10. Success

> A person can see, before anything is sent, exactly where each prompt is going
> and which rule decided — and the ones that must not leave, do not, whether or
> not anything downstream is working.

Not "the router picks the cheapest adequate model". That is the easy half, and
the literature already measures it. The half nobody ships is the one where the
decision is legible and the failure direction is the safe one.

---

## References

- *Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey* — arXiv 2603.04445
- *PRISM: Privacy-Aware Routing for Adaptive Cloud-Edge LLM Inference via Semantic Sketch Collaboration* — AAAI 2026, arXiv 2511.22788
- *RouterArena: An Open Platform for Comprehensive Comparison of LLM Routers* — ICLR 2026
- *RouteLLM: Learning to Route LLMs with Preference Data* — arXiv 2406.18665
- *BEST-Route: Efficient LLM query routing via multi-sampling* — arXiv 2506.22716
