# What this design cannot currently do

A sober re-reading of iriguchi against what it can be shown doing, rather than
against what it says it does. Everything below is a measurement or a check that
was run; the commands are given so a reader can disagree with the number rather
than with the sentence.

The findings are ordered by how much of the product they remove.

---

## F1. Half the routing design changes two outcomes in a hundred and fifty-five

iriguchi's story has two axes. Sensitivity is a **veto**; complexity is a
**preference** (ADR-0003). The veto is measured, argued about, and has its own
section in `measurements.md`. The preference has never been shown deciding
anything, and over the corpus it very nearly does not.

Over all 155 cases, with both destinations available:

| what decided the route | cases | |
|---|---:|---:|
| the veto removed external | 49 | 24.9% |
| complexity kept it local | 144 | 73.1% |
| **complexity sent it out** | **4** | **2.0%** |

Split by where the case came from:

| source | n | veto | local | external | median length |
|---|---:|---:|---:|---:|---:|
| `borrowed:mamori` | 134 | 37 | 97 | **0** | 34 chars |
| `generated` | 21 | 9 | 10 | 2 | 44 chars |
| `requests` | 42 | 3 | 37 | 2 | 78 chars |

**The borrowed 134 cannot exercise the axis at all**, and the reason is visible
in one number: their median length is **34 characters** and their longest is 85.
They are mamori's PII samples — a name, a particle, an email address. A
complexity estimator reading `田中さんに tanaka@example.com で連絡` has nothing
to estimate, because that is not a request for work. It is a string containing
personal data, which is what it was written to be.

So 86% of the corpus is on loan from a project measuring a different thing, and
it measures the veto well because the veto is what it was built for.

### The corpus now exists, and the axis is measured for the first time

`requests` is 42 invented prompts that are **requests for work** rather than PII
strings: proofreading and reformatting at one end, proofs and architecture
trade-offs at the other, in both scripts, with the long-and-easy and
short-and-hard traps preserved. Bands are labelled against the definition
`tools/measure_router.py` already puts to a model, word for word -- *low: a
small local model will answer this adequately; moderate: it will probably manage
but a larger one would answer better; high: it needs the larger model* -- and
deliberately **not** by what iriguchi's rules would say, because grading an
estimator against its own output measures nothing.

The result, on those 42 alone:

| labelled ↓ / iriguchi said → | low | moderate | high |
|---|---:|---:|---:|
| **low** | **14** | 1 | 0 |
| **moderate** | 12 | **2** | 0 |
| **high** | 7 | 4 | **2** |

**Band accuracy 42.9%, against 35.7% for always answering `low`.** On the 21
generated cases the same estimator scores 81.0%.

The aggregate understates how one-sided this is. `low` is nearly perfect at
14/15: the estimator recognises easy work. **`moderate` is 2 of 14 and `high` is
2 of 13** -- eleven of the thirteen hardest prompts were kept local, seven of
them called `low` outright.

The cause is visible in the rule set. Every escalating marker is a phrase --
`prove`, `compare`, `why`, `証明`, `比較` -- so **the estimator detects difficulty
only when the request announces it**. *"Plan the migration of this table with
zero downtime, including the rollback path and what makes it irreversible"* names
no marker and scores zero.

That is not a bug in a rule. It is the residual
[ADR-0004](adr/0004-decide-before-the-request.md) predicted in writing -- semantic
features need a model, this estimator is built from the complementary half, and
is "by construction the weaker of the two axes." **The claim was always there;
until now there was no number attached to it.**

### What is not the fix

Lowering `high_at` until the axis fires. `tools/calibrate.py --sweep` already
measured that curve through the router:

| `high_at` | prompts routed outward |
|---|---:|
| 0.7 (default) | 1.3% |
| 0.2 | 6.5% |
| 0.0 | 70.3% |

The axis can be made to fire as often as anybody likes. That is not evidence
that it fires *correctly*, and tuning a threshold until the rate looks
respectable is the move ADR-0003 exists to refuse. A number chosen to make a
graph look busy is not a measurement.

### What the fix is

A corpus of **requests** — the thing a person actually types into a router —
against which the complexity band can be scored the way sensitivity already is.
Until that exists, the honest statement is that iriguchi has one measured axis
and one designed one, and the README should say so.

Reproduce: `python tools/which_axis.py` and `python tools/calibrate.py --sweep`.
Both run against the committed corpus with no model and no network. The rows
above are recomputed on every test run by `tests/test_the_published_numbers.py`,
so a corpus that grows moves them here rather than leaving them true-as-of-once.

---

## F2. The external half is unreachable for everybody who is not on this machine

`ask --external` protects an outbound prompt through mamori. There is no
unprotected fallback, by construction — *the alternative to protecting a prompt
is not sending it* — so `MamoriChannel.__init__` refuses when mamori is absent.
That refusal is correct and is not the finding.

The finding is what happens next. Checked against PyPI:

| distribution | on PyPI |
|---|---|
| `mamori` | **no (404)** |
| `iriguchi` | no (404) |
| `tsumugi` | yes — **1.1.1, an unrelated genomics project** |

And what iriguchi prints as the remedy:

    mamori is not installed (`uv pip install -e ../mamori`)

`../mamori` is a relative path that resolves on a machine with both checkouts
side by side. There are no such machines other than this one.

Verified end to end: a fresh venv, `iriguchi` installed from a built wheel and
nothing else, `EXTERNAL=1` with a real URL and a real model —

    REFUSED  EscalationRefusedError: mamori is not installed, so there is
    nothing to protect an outbound prompt with.

So the external destination is **asked for by 1.3% of the corpus (F1) and
openable by 0% of users**. Everything downstream of it — the escalation channel,
the protection record reader (ADR-0013), `ask`'s upstream (ADR-0014), most of
what ADR-0012 exists to protect — is code no user reaches.

### The options, which are the owner's to choose between

1. **Publish mamori.** The escalation path becomes real, and iriguchi's install
   story becomes `pip install iriguchi mamori`.
2. **Say it is out of scope for v0.1.** The README leads with the local router,
   the external route is documented as requiring a sibling checkout, and the
   roadmap moves it to the release where mamori ships. Costs nothing and stops
   the README describing a door nobody can open.
3. **Vendor the protection.** Rejected on sight — it would fork a security
   boundary and give iriguchi a second copy of somebody else's threat model.

(2) is available immediately and does not foreclose (1).

---

## F3. `doctor` called that unusable destination "available" — fixed

Same clean venv, before the fix:

    external service  available    some-model at https://example.invalid/v1

Every `ask` against that configuration was refused. `_endpoint` already avoided
this defect for a *missing endpoint* — its own docstring names it, *a true
sentence that sends the reader to fix the wrong thing* — and did not check the
other thing `ask` requires.

**Fixed.** Four states rather than three. `doctor` now prints:

    external service  available for routing, nothing can protect an outbound prompt

with a paragraph saying that `route` will still say a prompt may leave while
`ask --external` refuses, which is the disagreement somebody would otherwise
meet at the moment of sending.

The two blockers share one framing — *available for routing*, then what stops
the asking — because that half is true of both: routing needs no endpoint and no
protection, and it works. The first version said `cannot be used` and took
precedence over the endpoint message, which **hid a gap a test was already
checking for**. CI caught it; the lesson is that a new state added at the front
of a chain silences every state behind it.

---

## F4. The default scanner's documented remedy is the uninstallable package

`missed findings` is **61.7%**, and
`measurements.md` argues correctly that this is the fallback working as
specified rather than a bug: it has no model, and mamori's corpus is full of
bare names, English names, company names and addresses.

The remedy it prints is *Install mamori for a scanner that does not.*

F2 makes that advice unfollowable. A user reading `doctor` is told the scanner
misses most of what matters and pointed at a package that does not exist for
them. The number is honest; the sentence after it is not actionable, and one of
F2's options has to resolve it.

**Half-fixed.** All three places that print the remedy now say *mamori is not on
PyPI, it needs a checkout beside this one*, so a reader is no longer left to try
`pip install mamori` and conclude the advice is stale. The comment above the
message had said this since it was written; the string somebody actually reads
did not, which is the whole failure in one line — **a true fact in a comment is
a fact the user never gets.** It does not make the package obtainable. That is
still F2's to answer.

---

## F6. Every tuned number was unreachable, and one of them meant two different things

Asked directly: *are there thresholds that will not survive contact with a
release?* Yes, and two kinds.

### Unreachable

`RulesEstimator` had **no `__init__` at all**. Not a narrow interface — no
interface. Every number that decides anything was a module-private constant:

    _LONG_INPUT = 600            _DENSE_WORD_LENGTH = 7.0
    _ESCALATING_WEIGHT = 0.45    _DENSE_MIN_WORDS = 20
    _MIXED_SCRIPT_MIN_SHARE = 0.1
    and 0.3, 0.25, 0.2, 0.35 written inline at the call sites

A deployment whose traffic did not look like this corpus had exactly one option:
fork the library. That is not a tuning story, and every one of these was chosen
against 155 cases, 134 of which are borrowed PII samples (F1).

**Fixed.** `RulesSettings` carries all of them with the same defaults, validated
at construction, plus `marker_weights` for per-rule overrides — which is the knob
that matters after release, because it lets one rule be retuned without touching
the other twenty. `route(text, estimator=RulesEstimator(RulesSettings(...)))`
reaches it, and a name still works for the CLI.

Refused at construction rather than at use: a weight above 1 makes
`1 - prod(1 - w)` produce a negative factor and a score outside [0,1], which the
published schema then rejects — three layers from the line that caused it.

### Meaning two different things

`_LONG_INPUT = 600` counted **code points**, and the same request is about half
as many code points in Japanese:

| the same request | code points | east-asian width |
|---|---:|---:|
| `Please refactor this authentication module.` ×15 | 660 | 660 |
| `この認証モジュールをリファクタリングしてください。` ×15 | **375** | **750** |

The English one crossed 600. The Japanese one did not. **A Japanese user had to
write roughly twice as much to reach the same band** — in a project written in
Japanese, about Japanese prompts. Nobody chose that; it fell out of counting
characters.

**Fixed** with `unicodedata.east_asian_width`: Wide and Fullwidth count two, the
convention every terminal uses to align a CJK column. Stdlib, no dependency, and
a proxy for information content rather than a measurement of it. Ambiguous-width
characters count one, because their width depends on the reader's locale and
guessing East Asian for Greek would break this in the other direction.

The corpus is unchanged by this — its prompts have a median of 34 characters and
come nowhere near 600 in either unit — which is itself F1 restated: the corpus
could not have caught this.

### The one that is recorded rather than fixed

`complexity.dense-vocabulary` matches on an **ASCII-only** word pattern, so it
cannot fire on Japanese or Chinese at all. Its comment admitted the rule was
wrong about German and did not mention that it is silent on the language this
project is written in.

The obvious counterpart was measured and **rejected**. Kanji ratio is a language
detector wearing a density costume: over this corpus its 90th percentile is 0.71
and every case up there is ordinary Chinese prose, because Chinese is ~90% hanzi
whatever it is about. A signal that fires on an entire language is worse than a
missing one.

So the gap stands, documented in the code, and is part of why the complexity axis
is the weaker one.

### What was checked and found sound

| number | verdict |
|---|---|
| band boundaries 0.3 / 0.7 | already `Thresholds`, already calibratable by `tools/calibrate.py` |
| entropy 3.0 / 4.5 bits | derived and published in `measurements.md`, with the reasoning |
| Presidio `score_threshold` 0.5 | Presidio's own knob, calibrated by its authors, passed through |
| `openai_compatible` 8 / 600 / 1024 | transport limits, not detection |

## F5. `tsumugi` is taken on PyPI

Not an iriguchi defect — recorded here because the family shares a naming
scheme and this is where the check was run. `tsumugi` 1.1.1 on PyPI is
*TSUMUGI: Phenotype-Driven Gene Network*, unrelated. Any publishing plan for
the family needs a different distribution name for that project, or an
namespace. `iriguchi` and `mamori` are unclaimed.

---

## What this audit did not find

Worth stating, so the list above is read as a bounded result rather than as
everything that could be wrong:

- No leak. The invariant tests and the corpus leak rate are unchanged.
- No architectural drift. The six import contracts and the AST layering test are
  green, and the three-way agreement between `ALLOWED`, `AGENTS.md` and
  `.importlinter` holds.
- Nothing wrong with the veto. It is the measured half and it measures well.

The findings are all one shape: **the parts of iriguchi that are hard to
demonstrate are the parts that have not been demonstrated.** That is not a
coincidence and it is not dishonesty — it is what happens when a corpus is
borrowed from a neighbour who was measuring something else.
