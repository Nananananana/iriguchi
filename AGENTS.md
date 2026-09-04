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
| `config.py` | `domain`, `ports`, `application`, `infrastructure` |
| `interfaces/` | everything above, `config` included |

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
- **After a merge: pull, `git log --oneline -1`, and run the suite on `main`.**
  Written down because it was a habit, and a habit is not installed — this file
  had nothing about verifying a merge at all, which is worse than kiseki's and
  musubi's `confirm "Squashed and merged"` even though that line reads a
  mechanism's report rather than a result.

  What it proves: the squash commit exists, and the tests that came with it pass
  where they landed. What it does not: that the *content* is what the PR
  contained. Reading a file for a phrase from the change is the cheap version of
  that, and this is what caught #33 as genuinely landed rather than merely
  merged.

  **A stronger script exists** in the release role's working directory and is
  deliberately not adopted here. Replacing something weak and installed with
  something strong and uninstalled is the same trade as a weak check that looks
  like coverage, run backwards — and the release role reached that conclusion
  about distributing it before anybody asked. Recording the practice is not the
  same act as upgrading it, and only the first is happening.
- A PR handed to the release queue may be **taken back by its author after 30
  minutes**. That is a threshold for the waiting side, not a promise from the
  queue: past it, the author is right and the queue is slow. It rests on one
  measurement (#33, 289 seconds end to end) and is a chosen number, not a
  derived one.
- **A `parametrize` over an empty list is green.** pytest's default marks an
  empty parameter set `skip`, so an architecture guard whose files come from a
  glob retires silently when the glob finds nothing — a renamed package, a typo
  in a root. `empty_parameter_set_mark = "fail_at_collect"` closes that for
  every parametrized case; a plain `assert not <derived set>` is not covered by
  it and needs its own floor. Measured before it was fixed: pointing
  `PACKAGE_ROOT` at a directory that does not exist left the layering, purity
  and sibling checks collecting **zero tests each**, and the run stayed green.
- **Anchor an edit on text this branch has, and `grep` for it before writing
  the script.** Three times in one session an edit keyed on a line that lived
  on a different unmerged branch. The third time, the anchor was *this rule*,
  written an hour earlier to prevent exactly that. An assertion mid-script is
  not enough: it fires after earlier edits have been written, so half the
  documentation lands. Check every anchor first, then apply.
- **All tests must pass before any commit.** One failure means stop and
  investigate, not proceed.
- Test file names are unique across the repository — tests are not a package and
  duplicate basenames break collection.
- Any test that invokes the CLI isolates itself: chdir to `tmp_path` and strip
  `IRIGUCHI_*`. A CLI test that writes into a developer's real configuration is
  a bug waiting in every future test file.
- **`cp932` is the console the reader has, and `PYTHONUTF8=1` is the one you
  have.** Every command here runs with that prefix, so an encoding failure is
  invisible during construction, and CI cannot see it either -- a runner's
  locale is UTF-8, and more runners of the same kind do not make a machine
  capable of the failure. `tests/test_console_encoding.py` *builds* the console
  instead of looking for characters, which is why it runs anywhere. A scan of
  this repository's string literals finds nothing and never could: the
  characters come from the prompt.
- **`python tools/mutate.py` before believing the suite.** Every guard here has
  been broken by hand once; mutation testing does it exhaustively. A survivor is
  not a bug — it is a sentence the suite cannot tell from the truth — and the
  first run turned 22 of them into two real gaps and twenty pieces of noise
  worth naming.
- **A menu entry carries its price.** Every registry choice stores the trade it
  makes, and a test refuses one shorter than ten words. A list of algorithm
  names with no costs beside them is the thing this project exists not to be.
- **Two questions about a check, not one.** *How many files did the type checker
  see* is the first, and widening `files` answered it. *How many of those can a
  user see* is the second, and `py.typed` is what answers that: without the
  marker a consumer's type checker skips the package and every annotation here
  reaches nobody. It is asserted in the wheel job, on the artefact a consumer
  installs, because a marker present in the repository and absent from the wheel
  looks identical from inside.
- Checks before every green commit: `uv run pytest -q`, `uv run mypy`,
  `uv run lint-imports`, `uv run ruff check --fix .`, `uv run ruff format .`,
  `uv run pre-commit run --all-files`. If pre-commit rewrites anything,
  `git add` and run it again — a commit whose hooks failed did not happen.
- **`uv run mypy`, with no path.** This line said `uv run mypy src` for two
  releases, and `pyproject.toml` said `files = ["src/iriguchi"]` — two places
  agreeing on a scope narrower than what they protect, which is why nobody
  noticed. A path argument *overrides* `files`, so widening the setting alone
  would have changed nothing for anybody following this line.
- **`uv run mypy --platform linux` before pushing anything that touches
  `tools/`.** The lint job runs on Linux while the test matrix runs both, so a
  Windows-only probe type-checks clean here and fails there. That flag
  reproduces the CI job locally in about a second, and it is cheaper than
  finding out from a red check.
- **`lint-imports`, never `python -m importlinter.cli`.** The module form prints
  nothing and exits 0 whatever the contracts say; CI ran it for the project's
  whole life, so the six import contracts had never been enforced anywhere but a
  developer's machine. `tests/test_ci_gates.py` keeps it from coming back.
- **An exit code is evidence only once something has been shown to make it
  non-zero.** That gate's silence was seen and dismissed earlier in the same
  session, because it exited 0. Every guard added this week was checked by
  breaking the thing it guards and watching it fail.
- **And "it went red" is not "the guard worked" — check it failed the way you
  meant.** Renaming the seam job made every test in `test_ci_seam_job.py` die at
  `job_block` with a bare `StopIteration`: a failing suite in which not one
  assertion had run. `job_block` now states its own failure, and a test pins the
  old shape *by exception type*. tsumugi found the mirror image — an injected
  TOML error failing pytest at collection, logged by a `returncode != 0` check
  as a confirmed failure of an assertion that never executed.
- **Verify a guard by *removing* what it guards, not only by changing it.** A
  loosened thing still parses; a deleted one does not, and the difference is
  where seven guards were found crashing instead of asserting. Every
  break-and-watch run in this repository before that had injected a changed
  value and never an absence — a blind spot shaped exactly like the thing being
  guarded against.
- **Which of these rules are commands and which are only sentences**, because a
  rule you can quote is not a rule you have installed:

  | rule | enforced by |
  |---|---|
  | `lint-imports`, not the module form | `tests/test_ci_gates.py` |
  | the seam job is pinned and intolerant | `tests/test_ci_seam_job.py` |
  | absent is not broken | `mamori_state()` and its tests |
  | a decision carries no value | `tests/test_domain_values.py` greps the output |
  | a rule id is a topic (ADR-0012) | **nothing** |
  | a guard must not match its own prose | **nothing** |
  | pin a hypothesis example before editing the test | **nothing** |
  | verify by removal, not only by change | **nothing** |

  The bottom four are judgement and stay judgement. Saying so is the point: a
  reader should not have to work out which half of this file is machinery.
- **A third column exists and is easy to miss: rules somebody else holds.** Two
  of iriguchi's guarantees are not enforced here at all —

  | | held by |
  |---|---|
  | `mamori.protection-scope/1` means what it meant | mamori's contract freeze |
  | a credential is blocked, not tokenised | mamori's ADR-0002 |

  Both are load-bearing. The escalation channel treats `PolicyViolationError` as
  its last gate, so if mamori stopped blocking credentials that gate would
  vanish silently; and the refusal logic reads fields whose meaning mamori
  defines.

  **The pinned sha is the mechanism**, and only for half of it. Raising the pin
  runs the seam tests against the new mamori, so a *behavioural* change is caught
  there: `test_a_credential_is_the_last_gate` and the round-trip tests exercise
  the real thing. A change in what a *field means*, without a contract bump, is
  not caught — the three refusal tests use synthetic records, and a synthetic
  record keeps agreeing with itself. That gap is real and is left open
  deliberately: closing it would mean asserting mamori's semantics from here,
  which is the coupling the document exists to remove.
- **A check whose subject includes the prose about the check passes for the
  wrong reason.** Five times now: `siblings` in a comment explaining there is no
  siblings extra; `continue-on-error` in a comment explaining its absence;
  `python -m importlinter.cli` likewise; `@example` against a corpus full of
  `@example.com`; and a test asserting `"StopIteration" not in str(error)`
  against an error message that explains it replaced a `StopIteration`. Strip
  comments, match by type, or match on something the explanation cannot contain.
- Windows: set `PYTHONUTF8=1`. This project reads Japanese text in every test.
- Tests that call a real model carry the `llm` marker and are excluded from CI
  by default (`addopts = -m 'not llm'`); run `uv run pytest -m llm` before
  merging model-adjacent changes.
- Read-only dumps for an assistant go **outside** the working tree.
- **Pin a hypothesis counter-example as `@example` before touching the test
  body.** The example database is keyed by a digest of the test function's
  source, so adding a `print` or changing an assertion message silently orphans
  every counter-example the test has accumulated — no error, no warning. There
  are currently **no** `@example` decorators here and two files using hypothesis,
  which means anything it has ever found lives only in gitignored
  `.hypothesis/` and has never been seen by CI or by anyone else.

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

- Version `0.1.0.dev0`. v0.1 is built and headless; **v0.2's escalation channel
  is in**, so `ESCALATED` is no longer a verdict with nothing behind it.
- **License: Apache-2.0. Python: 3.12+. Runtime dependencies: 0**, checked in CI
  by installing without extras and asserting nothing came along.
- **The commands that exist** are `route`, `config`, `doctor`, `demo`, `eval`.
  `iriguchi ask` does not, and neither does any model or ollama adapter — a
  sibling session built a GPU schedule around running it, because a roadmap item
  name is shaped exactly like a command name and reads as one. `iriguchi --help`
  is the authority; a plan is not a program.
- **Built:** `domain/` — `Span`, `Destination`, `Route`, `Finding`,
  `Sensitivity`, `Signal`, `Complexity`, `Reason`, `Removal`, `RoutingDecision`,
  `RoutingPolicy` — and `errors.py`. 100% covered, `mypy --strict` clean, and the
  invariants fuzzed by hypothesis in `tests/test_routing_properties.py`. Nothing
  is re-exported from `iriguchi/__init__.py`: a top-level name is a promise about
  a public API, and the API is not settled until something outside the domain
  uses it.
- **The rules are executable.** `tests/test_architecture.py` holds `ALLOWED`,
  which is the authority for the layer table above; the table describes it. The
  domain's standard-library imports are an **allow-list**, not a deny-list, so a
  new one is a deliberate line in that file. A separate test names the stdlib
  modules the domain may never import and says why for each — `os` and `pathlib`
  because a domain that can open a file can be told a different answer by it,
  `time` and `random` because a decision is a function of its inputs.
- **`tests/conftest.py` poisons the network for the whole suite**, autouse.
  `import-linter` proves nothing *imports* a socket; this proves nothing *calls*
  one, which is a different claim — a call reached through `urllib` names no
  socket in this repository. The poison is an `AssertionError`, not an
  `OSError`, because fail-closed code is entitled to catch `OSError` and fall
  back, and that is the behaviour worth catching. v0.2's adapters opt out with
  `@pytest.mark.network` per test; the default is never relaxed.
- All four guards were checked by injecting a violation of each and confirming
  red — including a function-level `import urllib` inside `RoutingPolicy.decide`,
  which is how a forbidden dependency actually arrives, because it looks local
  and harmless.
- Two combining rules to know before editing either axis. Complexity signals
  combine as independent evidence (`1 - prod(1 - w)`), not by adding: bounded by
  construction and monotonic, so a prompt that trips forty rules needs no cap —
  and a cap is what makes the fortieth signal free while the fourth was not. On
  top of that, **two or more escalating signals reach the top band regardless of
  the score**, because the case weighted scoring is worst at is a prompt asking
  for two hard things at once, where each marker is individually cheap and the
  sum lands in the middle.
- `SignalKind` has no `SEMANTIC` member, deliberately. The literature is
  consistent that semantic features dominate difficulty prediction; they need a
  model, and ADR-0004 refuses a model in the deciding path. Leaving the name out
  keeps the refusal visible. **The complexity axis is the weaker of the two by
  construction**, which is affordable only because it chooses between
  destinations that are already safe.
- **`ports/` holds two protocols, not the six the design names.** A port is written
  when something implements it and something calls it; the rest wait for the
  version that gives them an adapter (ADR-0011). The set of destinations a
  machine has is **configuration in v0.1, not a probe** — `route --dry-run` is
  told what is available and does not go and look, which is what lets the whole
  of v0.1 run with the network poisoned.
- `tests/contracts.py` holds a conformance suite per port. Its clauses are mistakes
  somebody has made, not a restatement of the protocol, and `tests/test_port_contracts.py`
  runs each clause against something built to break it — a suite nobody has seen
  fail might be checking nothing. **The offsets clause states what it misses**: a
  bounds check catches normalization that expands (`㍿` → four characters) and
  cannot catch normalization that contracts (`e` + U+0301 → one), because a wrong
  span is then still in bounds. No generic clause can; an adapter's own test has
  to assert on the value under the span.
- **The fallback scanner is specified over-detection, not tolerated over-detection**
  (ADR-0005). `tests/test_fallback_scanner.py` has three sections and the third
  matters most: *what it catches*, *what it also catches* — order numbers, epoch
  timestamps, a title swept up with a name — and *what it misses*. A test in the
  last section starting to pass is good news; move it upstairs rather than
  deleting it. The largest gap is a Japanese name with no honorific.
- The scanner's stoplist (`お母さん`, `皆さん`, …) is what keeps the external
  route reachable at all. It is permanently incomplete and does not need to be —
  everything it misses is an over-detection. **The honorific rule's run is lazy**
  and that is not a style choice: greedy, it matches `皆さんお疲れ様` in
  `皆さんお疲れ様です`, which is neither stoplist entry, so the stoplist silently
  protects nothing.
- **Entropy thresholds are measured** (`docs/measurements.md`,
  `tools/measure_entropy.py`): 4.5 bits for the base64-ish charset, 3.0 for hex
  because hex tops out at 4.0, and **digits excluded entirely** because ten
  symbols cap them at 3.32 and no threshold separates a card number from an order
  number. Entropy also cannot reach a short structured key — `AKIA…` measures
  3.68, below a documentation URL — so the vendor-prefix rule is the half that
  catches those, not an optimisation on top.
- **Normalization keeps an offset map** (`infrastructure/normalization.py`), folding
  one character at a time. Full-width folds, so `ｔａｎａｋａ＠…` is found; a
  combining mark does *not* compose, so those offsets stay one-to-one. The cost
  is that a pattern written against composed `café` misses the decomposed form.
- The rules estimator is **the weaker of the two axes by construction**, and its
  module docstring says so first rather than last. Semantic features dominate
  difficulty prediction and they need a model, which ADR-0004 refuses in the
  deciding path — so this is built from the complementary half alone. Affordable
  only because complexity chooses between destinations sensitivity already
  cleared.
- **Escalating weights are 0.45 for a reason.** One reaches the middle band; two
  combine to 1 - 0.55² = 0.6975, *under* the 0.7 threshold, so the short-circuit
  is what carries them to the top. Raising those weights until the score reaches
  the band on its own would make the short-circuit untestable decoration, and a
  test asserts the gap.
- Two rules exist for the ADR-0007 traps and should be read as a pair:
  `long-input`'s weight is deliberately too small to reach the top band alone
  (*long and easy* — a pasted log), and the escalating families exist because
  nothing lexical sees *short and hard* (eleven characters asking for a proof).
- `dense-vocabulary` is the weakest rule in the project and is documented as a
  proxy: real rare-word rate needs a frequency list, and a wordlist is a
  dependency in everything but the packaging. It counts **ASCII** tokens, so it
  is blind to Japanese technical prose; `mixed-script` is what notices that, and
  only when English terms are mixed in.
- **A proposer's failure is not a failed request.** `application/routing.py`
  catches a `ScanError` and turns it into a restriction spanning the whole
  prompt, so the route becomes local and a reason names the scanner that broke
  (ADR-0002: *the most restrictive route available, not the most useful one*). A
  broken scanner costs the external route, not the afternoon. It also catches
  non-`ScanError` exceptions broadly and deliberately — the alternative is that a
  `KeyError` in somebody's rule table becomes a leak.
- An estimator failure is reported too, though nothing dangerous follows from
  it: no signals is already the lowest band. Reported because a decision that
  quietly lost an axis looks exactly like one where that axis had no opinion.
- **The one failure nothing can catch** is a scanner that returns `()` while
  lying. `TestTheOneItCannotCatch` shows that prompt going out. That is not a
  defect in the use case — it is the consequence the port's raise-don't-return
  rule exists to prevent, kept as a test so anybody tempted to relax the rule can
  see what it buys.
- `Reason.sort_key` orders spanless reasons before spanned ones, and within each
  group by source then rule. **There is no notion of importance**, deliberately:
  ordering by importance is a presentation decision and belongs to `--explain`.
- **The corpus is 155 cases**: 21 generated with adversaries planted, 134
  borrowed from mamori's labelled detection corpus. Borrowed by a tool that runs
  once and commits its output — `evaluation/` may not import mamori, and finding
  an installed package's data directory requires exactly that. The corpus works
  with mamori absent.
- **Read `missed findings` before `leak rate`.** The scorer originally reported
  a 0% leak rate while the scanner was clearing 65% of the must-stay-local
  cases: those prompts were easy, complexity chose local on its own, and a miss
  that never became a route is invisible end to end. A metric satisfiable by
  luck is worse than no metric, because it gets quoted.
- **63.5% missed findings is published, not fixed.** It is the measured form of
  ADR-0005's "install mamori". The test asserts it as a *range* — the upper
  bound catches a collapse, the lower bound catches somebody quietly making the
  fallback clever, which is how it would stop being the dumb thing it is.
- A case labels sensitivity and band; **it never labels a route**. The scorer
  asks the policy what the labels imply. Writing the route into a fixture would
  copy the policy into the corpus, and then a policy change would need a corpus
  edit to stay "correct" — which is how a corpus stops being evidence.
- The eval gate did its job on its first run: it found the credential rule
  required `:` or `=`, so it was blind to `パスワードは hunter2 です`. Fixing that
  cost precision, and tightening the captured value bought it back. Both halves
  are tests, and `docs/measurements.md` has the before/after.
- **`route --explain` output is a golden test.** An explanation nobody diffs is
  an explanation that drifts, and this is what somebody reads when deciding
  whether to trust the tool. Asserted whole rather than by substring: the
  interesting failures are things that *disappear*, and a substring check cannot
  see an absence.
- **Ordering reasons for reading happens in `interfaces/cli/render.py`, not in
  the domain.** `Reason.sort_key` is a total order and not a useful one for a
  person; the domain has no notion of importance and giving it one would be a
  domain change for a presentation concern.
- Exit codes distinguish three things: `0` a decision, `2` a decision that was a
  refusal, `1` no decision. **A refusal is not a failure** — a caller that cannot
  tell them apart will retry a refusal forever.
- Availability is `--local` / `--external` or `IRIGUCHI_*`, and **both default to
  off**. Somebody who has configured nothing gets refusals, not a router
  assuming a model exists. Unknown `IRIGUCHI_*` keys are refused, never ignored.
- **mamori is a scanner adapter and nothing else yet.** It asks with a
  *permissive* policy, as mamori's own `inspect` does: the default policy blocks
  a credential, which would arrive as "the scanner broke" — same route, wrong
  stated reason, and a wrong reason reads as authoritative. Permissive means
  mamori reports and iriguchi's policy decides, which is ADR-0005 exactly.
- **`--scanner mamori` is opt-in even when mamori is installed.** Changing the
  scanner changes what leaves the machine, and that is not a thing to inherit
  from what happens to be on the system. Asking for it without it installed is
  an **error**, never a silent downgrade: somebody who passed the flag is
  relying on it finding what the fallback cannot.
- Two `.importlinter` edges are ignored, with the reason in the file: the
  contract sees `interfaces -> config -> mamori_scanner -> mamori` and cannot
  see that every `import mamori` is inside a function. The guarantee it was
  protecting is asserted for real in `tests/test_mamori_absent.py`, which blocks
  the import and drives the whole CLI, and in the CI job that installs the wheel
  with no extras and runs it.
- **ADR-0012: a decision inherits the classification of its prompt.** ADR-0006
  keeps values out of a `Reason`; that is not sufficient. `mamori.national-id at
  40-52` is a kind, a count and a length, and to a reader who does not hold the
  prompt it is a pointer to which one was worth reading. So nothing writes a
  decision to disk, nothing sends one anywhere, and there is no `--log-file` —
  the absence is deliberate, not unfinished.
- The mamori comparison (63.5% → 1.0% missed) is **measured on mamori's own
  corpus** and is not a general figure. The only data mamori has not seen is 6
  generated must-stay-local cases, which supports no miss rate at all.
- **`Case.source` is necessary and not sufficient.** It records who wrote a case;
  independence is a *relation*, not an attribute. The question is not "did the
  scorer write this" but **"could whoever wrote it see the rules being scored"**,
  and these six libraries share their design discussion — so a corpus borrowed
  from a sibling fails that test as surely as one written here. Not having
  written something is not the same as not having seen it.
- **Provenance is a field, not a sentence.** Each corpus file records the hands
  behind its *text* and its *labels* separately, and the loader refuses a file
  that does not say. It used to be prose in a `description`, which no loader can
  check and no reader can query. `unrecorded` is an explicit value: an empty
  field reads as *nothing to declare*, a word says *not written down*, and those
  are opposite claims about the same absence.
- **It was recorded while it was still a fact.** One hand wrote
  `tools/generate_cases.py` and that hand is known, so the entry states rather
  than guesses. tsumugi reached the same position with twenty cases whose value
  said `drafted` and where nothing recorded *by what* — the honest repair was
  then impossible and the dishonest one (a default) was one line away. **The
  window here closes the first time a model drafts a case**, because `generated`
  would then mean two things.
- **Generating does not launder provenance: the generator is a hand.**
  `tools/generate_cases.py` was written by whoever writes the rules, while
  looking at them. More cases from it raise the regression floor and cannot
  produce independence. `docs/measurements.md` used to propose exactly that as
  the fix for portability, and it was wrong.
- Consequently **every number in `docs/measurements.md` is a regression floor**,
  not a measured property of the world. What would be portable is cases whose
  *text* came from somebody who could not see these rules, labelled here
  afterwards — the two hands split. **iriguchi has no scorer-side refusal**;
  mamori built one (`report.as_evidence_for(subject)`) and it is the shape to
  copy if this is ever enforced rather than documented.
- **The escalation channel protects and does not send.** `prepare` returns what
  *would* leave; handing it to anybody is a separate call this port does not
  have, which is what lets `route --explain --dry-run` walk the outbound path.
- **The protection record is read and never kept** (ADR-0013). Reading it does
  one job: iriguchi only escalates when its own scanner said `CLEAR`, so anything
  mamori protects on the way out is something the scanner **missed**, and that
  becomes a `Reason` — a kind and a count, never a token, a scope or a policy
  hash.
- **Every disagreement with the contract is a refusal, never a partial read.** An
  unrecognised `contract`; a `mode` of `surrogate` or `mixed` (iriguchi
  understands `placeholder` only, and the schema requires such a consumer to
  refuse); `reversible` false or absent. None of these degrades to sending
  something less protected — there is no such path.
- **mamori's own block is the last gate.** It refuses to protect a credential
  rather than tokenising one, so a `PolicyViolationError` here means a scanner
  already missed one. Going round it would send the thing two layers exist to
  stop.
- `config.channel()` exists for the same reason `config.router()` does: the
  composition root is the one place allowed to name an adapter, and routing every
  caller through it keeps `mamori-is-an-adapter` to **one** ignored edge instead
  of one per caller.
- **Next, per `docs/proposals/0001-the-design.md` section 8:** six ports with
  conformance suites, the over-detecting fallback scanner, the rules complexity
  estimator, the CLI (`route`, `explain`, `config`, `doctor`, `eval`, `demo`),
  and the evaluation corpus with `tools/generate_cases.py`.
- **A rule id is a topic**, which is ADR-0012's amendment and the part most
  likely to be missed. `complexity.formal-reasoning` fires on a closed set of
  markers, so naming it says the prompt asked for a proof; three signals sketch
  the request. No value is quoted and it is still more than mamori's record ever
  says about a document, because mamori never describes what a document is *for*.
  The test is not "does this field hold a value" but **"would this be safe to
  write down as: this person asked about X"**.
- **Absent is not broken**, and a boolean cannot tell them apart.
  `mamori_state()` returns `ABSENT` / `BROKEN` / `AVAILABLE`. `doctor` may ask a
  boolean — it wants to know whether mamori can be *used* — but **a test gate
  never may**: it has to skip on absent and **fail** on broken. Gated on the
  boolean, `tests/test_mamori_scanner.py` disappeared entirely when mamori was
  installed and unimportable, and the build went green at the moment the only
  check of that boundary stopped running. akashi found the same shape in its
  drift check, swallowing an `HTTPError` as a connection failure.
- The same conflation produced two wrong messages, both the `policy.prefer-local`
  mistake again: `config` and the constructor said **"mamori is not installed"**
  to somebody whose install was broken, sending them to fix the wrong thing.
- `ImportBlocker` in `tests/test_mamori_absent.py` patches `find_spec` in **both**
  directions, so `absent` and `broken` are both testable whether or not mamori is
  on the machine. Without that, `absent` was untestable on a developer's machine
  and `broken` untestable in CI — and four tests failed the first time the suite
  ran in a genuinely mamori-free environment.
- **The seam job is the only place `tests/test_mamori_scanner.py` ever runs.**
  Nothing else in CI installs mamori, so before that job existed those tests had
  never executed anywhere but a developer's machine — including the run that
  produced the numbers in `docs/measurements.md`. The absent side was covered by
  two dedicated jobs and the present side by none.
- **That job asserts mamori is importable before running anything**, because
  every test in it skips when mamori is absent: a failed install would run zero
  tests and report success. `continue-on-error` is on the two steps *after* that
  assertion and never on the job. A sibling's release changing behaviour should
  tell us rather than block a merge, but "we could not install the sibling" is a
  different finding and must be red. **If a mamori release starts blocking work,
  pin the checkout to a ref — do not widen the tolerance.**
  `tests/test_ci_seam_job.py` enforces that split.
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
