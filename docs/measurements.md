# Measurements

**Status: current state.** What things actually cost, on real hardware, with the
scripts that produced them.

House rule, from tsumugi: *a number in a document is measured, or it is not
written*. The original specification contained two numbers that were not — 10 MB
resident and 1 ms startup — and these are the measurements that replaced them.
See [ADR-0008](adr/0008-the-invariant-is-the-warm-path.md) for what they changed.

Environment: Windows 11 Home 10.0.26200, x86_64, on a machine that was in
ordinary use — which turns out to matter, and is the second finding below.

## Resident memory

`tools/measure_memory.py`, working set, three stages, two interpreters.

| Stage | CPython 3.12.8 | CPython 3.14.6 |
|---|---|---|
| Bare interpreter, nothing imported | **12.8 MB** | **14.2 MB** |
| After `import tkinter` | 17.3 MB | 18.8 MB |
| After `Tk()` + one `Entry`, realised | **27.0 MB** | **28.8 MB** |

Repeated across several runs and both interpreters, these move by at most
0.4 MB. This is a stable measurement.

The specification's invariant was 10 MB or less. A CPython process that has
imported nothing is 28% to 42% over it, depending on the interpreter, and a
process with a window on screen is roughly three times it. The floor is not
reachable by writing less code, because it is not our code: it is the
interpreter, and then Tcl/Tk on top of it.

## Cold start

`tools/measure_startup.py`, seven fresh subprocesses per stage, minimum and
median reported.

Four runs, taken across a session in which the machine was variously idle and
running a test suite:

| Stage | best min observed | worst median observed |
|---|---|---|
| Bare interpreter (`python -c pass`) | **32 ms** | 796 ms |
| `import tkinter` | 52 ms | 456 ms |
| `Tk()` window realised and destroyed | **135 ms** | 1130 ms |

**The spread is the finding.** The same operation on the same interpreter
measured 32 ms once and a 796 ms median an hour later. Process creation on
Windows is dominated by things that are not the interpreter — the filesystem
cache, the antivirus scanner, whatever else is running — and a build gate on
this number would go red for reasons that have nothing to do with the change
that triggered it.

The specification's invariant was 1 ms. The *best* case measured here is 32
times that for a process that does nothing, and 135 times it for one that opens
a window. One millisecond is not a slow implementation of this design; it is a
different design, in a different language.

Running inside a virtualenv with an editable install adds roughly 100 ms on top
of every figure above (`.pth` files run an import hook at startup). Worth knowing
when reading a stopwatch during development; not a property of the shipped
thing.

## Shannon entropy, and where the thresholds came from

`tools/measure_entropy.py`. Every value is invented -- a real key in a file that
measures entropy would be a poor joke.

| | length | entropy | charset | entropy rule fires |
|---|---|---|---|---|
| an `sk-` style key | 32 | **4.81** | mixed | yes |
| a base64 blob | 48 | **4.68** | mixed | yes |
| a sha256 hex digest | 64 | **3.67** | hex | yes |
| a documentation URL | 47 | 4.14 | mixed | no |
| a source file path | 48 | 3.99 | mixed | no |
| run-together English | 31 | 3.72 | mixed | no |
| a long English word | 20 | 2.95 | mixed | no |
| a repeated character | 30 | 0.00 | hex | no |
| an AWS-style key id | 20 | 3.68 | mixed | no |
| an order number | 19 | 3.28 | mixed | no |
| a card-shaped digit run | 16 | 0.34 | digits | no |
| a uuid | 36 | 3.88 | mixed | no |

Four things follow, and all four are in the code as comments:

**4.5 bits for the base64-ish charset.** It is detect-secrets' default and the
measurement agrees with it *here*: it sits above the documentation URL (4.14) and
below both real secrets (4.68, 4.81). Note how little room that is. A threshold
chosen for a 0.5-bit gap is not a robust threshold, which is why the rule also
carries a length floor and why it is one rule among several rather than the
detector.

**Hex needs its own threshold, and it has to be lower.** A hex string cannot
exceed 4.0 bits per character by construction, and a real sha256 measures 3.67 --
so a 4.5 threshold would never fire on hex at all. It is 3.0.

**Digits are excluded from the entropy rule entirely.** Ten symbols cap the
entropy at log2(10) = 3.32, so any threshold low enough to catch a numeric secret
catches every order number and epoch timestamp. detect-secrets reached the same
conclusion. The over-detection is real and it belongs to the digit-run rule,
which admits to it in its own comment rather than hiding inside a statistic.

**Entropy misses short structured keys.** `AKIAIOSFODNN7EXAMPLE` measures 3.68 --
*below the documentation URL* -- and 4.5 bits is mathematically unreachable under
23 characters anyway. Format-aware prefixes are not an optimisation on top of
entropy; they are the half that catches these at all.

## The router, over the corpus

197 cases: 21 generated with adversaries planted (ADR-0007), 134 borrowed from
mamori's labelled detection corpus, and 42 **requests** written to measure the
complexity axis (see below). Run with `FallbackScanner` and `RulesEstimator`, no
mamori installed, no model, no network.

| | whole | generated | borrowed | requests |
|---|---|---|---|---|
| cases | 197 | 21 | 134 | 42 |
| **missed findings** | **61.7%** | | | 0.0% |
| leak rate | 0.0% | 0.0% | 0.0% | 0.0% |
| over-caution rate | 8.9% | 20.0% | 13.9% | 0.0% |
| route accuracy | 93.9% | 90.5% | 100% | 76.2% |
| band accuracy | 84.8% | 81.0% | 98.5% | **42.9%** |
| decision latency | 0.03 ms median | | | 3.10 ms slowest |

### Read the band row across, not down

**84.8% is the most misleading number on this page.** It is an average over
three corpora that are not measuring the same thing, and the 134 that dominate
it are 34-character PII strings where the answer is `low` every time -- so the
estimator scores 98.5% there by having almost nothing to decide.

On the 42 prompts written to actually exercise the axis it scores **42.9%,
against 35.7% for always answering `low`.** That is the number that describes
what the complexity axis does, and it is the reason
[`feasibility.md`](feasibility.md) F1 exists.

This is the same shape as the leak-rate finding below, one axis over: an
aggregate that looks healthy because the easy cases outnumber the informative
ones. The fix in both cases was to publish the number that can go wrong.

### Where the time went, and where it goes now

The latency row moved because the router was profiled rather than assumed. Over
a 6135-character prompt -- the longest in the corpus, and the shape that decides
the tail:

| | before | after | |
|---|---:|---:|---:|
| `scan` | 1.485 ms | **0.779 ms** | −48% |
| `estimate` | 3.208 ms | **2.187 ms** | −32% |
| whole decision | 4.711 ms | **2.989 ms** | −37% |

Two changes, both found by profiling and neither a guess.

**`normalize()` was 53% of an estimate.** It folds text per character on purpose
(the module docstring argues why), and for a 6135-character prompt that was 6135
`unicodedata.normalize` calls each returning their own argument, plus an offset
map holding `0, 1, 2, …`. Text that is already NFKC-normal -- which is nearly
all of it -- now returns immediately with an identity map represented as `None`.
A property test asserts the two paths agree on generated text rather than
trusting the argument for why they must.

**The width check was answering the wrong question.** `display_width` returned a
number and the caller only ever compared it to a threshold. Every character is
one column or two, so `n <= width <= 2n`, and both bounds settle the comparison
outright for anything but a narrow middle band. A long prompt now clears the
threshold on `len()` alone.

The slowest case is *higher* than the old published figure (3.07 ms against
0.18 ms) because that figure was measured before the corpus gained its 6135-
character case. The median halved. Both numbers come from `iriguchi eval`.

### The leak rate lied, and that is the finding

The first version of the scorer reported **0% leak rate** and nothing else about
coverage. Both of these were true at the same time:

- no must-stay-local case was routed out;
- **the scanner cleared 65.4% of them.**

Those prompts are short business prose, so the complexity axis chose local on
its own, and a missed finding that never became a route is invisible to an
end-to-end measurement. The same miss on a prompt that happens to ask for a
proof is a leak, with nothing about the scanner changed.

So `missed findings` was added and is printed *first*, and the leak rate now
carries the sentence "flattered by easy prompts" in the report itself. A metric
that can be satisfied by luck is worse than no metric, because it is quoted.

### What the corpus changed in the code

Running it found one rule bug, and fixing that found a second:

| | missed findings | over-caution |
|---|---|---|
| before | 65.4% | 15.7% |
| `は`/`が` as credential separators | 63.5% | **17.6%** |
| + the value may not start with kana or kanji | **63.5%** | **15.7%** |

The rule required `:` or `=`. Japanese writes `パスワードは hunter2 です`, so it
was blind to the language half this project's users write in. Adding the
particles cost precision immediately — `パスワードは変更しましたので` became a
finding — and requiring the captured value not to begin with kana or kanji
bought it back. Net: strictly better on both axes.

### 63.5% is not a bug, and it is not being fixed here

> **Scope.** The figures in this section were measured on the 155-case corpus,
> before `requests.json` added 42 more. They are kept as recorded rather than
> re-derived, the way the model rows are. The current whole-corpus figure is
> **61.7%**, and the scanner comparison that matters to a user today is in
> [What installing Presidio buys](#what-installing-presidio-buys).

The fallback scanner cannot find a name without an honorific, an English name, a
company name or an address. mamori's corpus is full of all four. **63.5% is the
measured form of ADR-0005's "install mamori"**, and it is published rather than
fixed by widening the fallback until the number looks respectable — which is
precisely how it would stop being the deliberately dumb thing it is supposed to
be.

`tests/test_evaluation.py` asserts it as a *range*, `0.4 <= rate <= 0.8`. The
upper bound catches a collapse; the lower bound catches somebody quietly making
the fallback clever.

## The band, against a model

`tools/measure_router.py`, 2026-09-02, ollama on this machine, **temperature 0**,
the 21 generated cases only. The 134 borrowed cases all carry `band: low`
assigned by these same rules and say nothing about this axis; including them
would have added 134 free agreements with the thing being tested.

[ADR-0004](adr/0004-decide-before-the-request.md) refused a model in the deciding
path and stated the cost as *"the learned routers are better at the cost-quality
trade and will stay better, and no amount of rule-writing closes that gap."*
**That is a claim about a magnitude, with no magnitude.** This is the magnitude.

**One case is 4.76 points**, so a difference under three cases — 14.3 points —
cannot be read from a run of this size. That floor is applied to every row rather
than left as a sentence, because a note above a table is a note a reader skips.

| | overall | vs the rules | low (14) | mod (3) | high (4) | **non-low** |
|---|---|---|---|---|---|---|
| always answering `low` | 66.7% | −14.3 **decidably worse** | 14/14 | 0/3 | 0/4 | **0/7** |
| **the rules, today** | **81.0%** | — | 12/14 | 3/3 | 2/4 | **5/7** |
| qwen2.5:14b-q4, cold | 76.2% | −4.8 undecidable | 13/14 | 0/3 | 3/4 | 3/7 |
| qwen2.5:14b-q4, briefed | 71.4% | −9.5 undecidable | 14/14 | 0/3 | 1/4 | 1/7 |
| qwen2.5:7b-q8, cold | 66.7% | −14.3 **decidably worse** | 11/14 | 3/3 | 0/4 | 3/7 |
| qwen2.5:7b-q8, briefed | **90.5%** | +9.5 undecidable | 14/14 | 3/3 | 2/4 | **5/7** |
| qwen3:8b, cold | 57.1% | −23.8 **decidably worse** | 8/14 | 2/3 | 2/4 | 4/7 |
| qwen3:8b, briefed | 85.7% | +4.8 undecidable | 13/14 | 1/3 | **4/4** | **5/7** |
| llama3.1:8b, cold | 28.6% | −52.4 **decidably worse** | 2/14 | 2/3 | 2/4 | 4/7 |
| llama3.1:8b, briefed | 71.4% | −9.5 undecidable | 12/14 | 1/3 | 2/4 | 3/7 |

*cold* asks the routing question in its own terms — would a small local model
answer this adequately. *briefed* hands the model iriguchi's own band
definitions. Every run is deterministic: the 14B cold run repeated gave 21/21
identical answers, so there is no run-to-run term in any of these figures.

### What it says

**No model configuration is decidably better than the rules. Four are decidably
worse. Six sit inside the floor, where nothing can be read either way.**

The two that appear to win — 90.5% and 85.7% — are **+9.5 and +4.8 points, both
inside three cases.** An earlier version of this page reported them as beating
the rules. They do not; the run cannot say.

**And the last column is where the headline was hiding something.** Two thirds of
the corpus is `low`, so an accuracy figure is mostly a report on the majority
class — while a router exists for the cases where a bigger model is worth
reaching for. On those seven:

    always answering `low`   **0 of 7**
    the rules                **5 of 7**
    qwen2.5:7b-q8, briefed   **5 of 7**   -- the same, at 90.5% overall
    qwen3:8b, briefed        **5 of 7**   -- the same, at 85.7% overall

**Both apparent wins are ties on the cases that matter.** Their whole margin is
in the `low` class, which the trivial baseline already takes for free.

The one genuine difference in the table is qwen3:8b briefed taking **4/4 on
`high`** against the rules' 2/4 — and it gives the two back on `moderate`, which
is why the column ends level. Four cases and three cases; neither is a finding.

**The wording of the question moves a model far more than the choice of model
does**, and more than the thing being argued about:

| | cold → briefed |
|---|---|
| llama3.1:8b | **+42.9** (9 cases) |
| qwen3:8b | +28.6 (6 cases) |
| qwen2.5:7b-q8 | +23.8 (5 cases) |
| qwen2.5:14b-q4 | **−4.8** (1 case) |

**Size is not monotonic either.** Briefed: 7B 90.5%, 8B 85.7%, 14B 71.4% — the
largest model is the worst, and the only one the briefing made worse. Whatever
"a learned router" names, it is not one object with an accuracy.

**The one thing the table decides** is that the rules beat the trivial baseline
by 14.3 points, which clears the floor by a hair — three cases exactly.

### What it does not say

**It cannot move ADR-0004.** That decision rests on auditability — *a router a
person cannot read is a router they cannot trust with the second kind of error*
— and a large gap would not have moved it either. What the number does is stop
the ADR borrowing the *form* of evidence for a decision that does not rest on
evidence. Its cost section is corrected accordingly: iriguchi is not measurably
behind here, and the previous wording said it was, permanently.

Carry these with any figure above.

1. **n = 21. One case is 4.76 points.** The floor is applied per row rather than
   described; `decidable()` returns three values and the middle one is
   *undecidable*, not *no difference*. bench wrote that shape and tsumugi
   carried it, on the grounds that a note in prose leaves the reader room and a
   type does not.
2. **This floor is arithmetic, not empirical.** It is what one case is worth, not
   what this machine's variability is. There is no run-to-run term to fold in
   here because the runs are deterministic, but on a machine where there is, this
   would be the wrong floor.
3. **The labels and the rules come from the same hand.** Both were written here,
   so the comparison is biased toward the rules by construction. A model beating
   them despite that would be the stronger finding; none does.
4. **One lineage and one machine.** Three of the four models are qwen. bench
   found no second family available locally.
5. **Selection by format-following does not apply here, and was expected to.**
   bench measured llama3.1 at 0/8 usable on long Japanese generation at
   temperature 0, and the concern was that testing only models which can follow a
   format selects for capability. On this task **every model answered with
   exactly one word, 168 of 168 replies**, llama3.1 included. Its format failure
   is a property of that task, not of the model.
6. **`iriguchi ask` leaves the temperature to the server.** These figures were
   taken at 0, chosen because at n=21 characterising sampling variance would take
   N runs of 21 and there is no budget for that in a corpus this size. They do
   not describe the setting the product runs under.

## What installing mamori buys

Both scanners over the same 155 cases. mamori under a permissive policy, as its
own `inspect` command uses, so that it reports a credential rather than refusing
one.

| | must-stay-local missed | may-leave over-detected |
|---|---|---|
| **whole corpus** | | |
| built-in fallback | 63.5% (66/104) | 15.7% (8/51) |
| mamori | **1.0%** (1/104) | 25.5% (13/51) |

That is ADR-0005's "install mamori", measured. It is also **measured on mamori's
home ground**, and the split says so:

| | must-stay-local missed | may-leave over-detected |
|---|---|---|
| **borrowed (134 cases, from mamori's own corpus)** | | |
| built-in fallback | 67.3% (66/98) | 13.9% (5/36) |
| mamori | 1.0% (1/98) | 33.3% (12/36) |
| **generated (21 cases, which mamori has never seen)** | | |
| built-in fallback | 0.0% (0/6) | 20.0% (3/15) |
| mamori | 0.0% (0/6) | 6.7% (1/15) |

**The 1.0% is not a general figure and must not be quoted as one.** mamori is
being scored against the corpus it was developed with. What the borrowed half
honestly shows is that the fallback is far worse than mamori *at mamori's own
task*; it shows nothing about either on a stranger's prompts.

The generated half is the only data *mamori* has not seen, and it has **six**
must-stay-local cases, which is too few to support any miss rate at all. Both
scanners score 0% on it, and that is a statement about the sample size.

The one number that survives both objections is the direction of the
over-detection trade, because it runs the same way on both halves: mamori finds
more and holds back more. On that half it holds back *less* than the fallback
(6.7% against 20.0%), which is the opposite of the borrowed half and is also six
cases' worth of evidence.

### Corrected: no part of this corpus is independent evidence about iriguchi

This section previously said the work to commission was *more generated
must-stay-local cases — the half of the corpus that no sibling has seen*, and
that doing so would make these numbers portable. **The second half of that was
wrong**, and it was wrong in the way this project keeps finding: a provenance
label that reads as independence and is not.

Two corrections, both from a cross-repository review:

**Generating does not launder provenance. The generator is a hand.**
`tools/generate_cases.py` was written by whoever writes iriguchi's rules, while
looking at them. Twenty-one such cases or two hundred, they measure whether the
rules do what their author intended — which is worth having as a regression
floor and is not evidence about anybody else's prompts. "mamori has not seen
them" and "they are independent of iriguchi" are different claims, and only the
first is true.

**Independence is a relation, not an attribute.** `Case.source` records who
wrote a case, and that is necessary and not sufficient. The question is not
*"did the scorer write this"* but *"could whoever wrote it see the rules being
scored"* — and these six libraries share their design discussion, so a corpus
borrowed from a sibling fails that test too. Not having written something is not
the same as not having seen it.

So, plainly: **the generated half is authored by iriguchi and the borrowed half
by a sibling that can read iriguchi's ADRs. Neither is independent of what it is
scoring.** Every figure in this document is a regression floor — a number that
has not been allowed to get worse — and not a measured property of the world.
mamori reached the same conclusion about its own leak rate.

**What would actually be portable** is cases whose *text* was written by somebody
who could not see these rules, with the labels applied here afterwards. Splitting
the two hands is the point: text from elsewhere and labels from us is the
cheapest arrangement that stops a corpus measuring its author's imagination. It
does not exist, and no amount of generating will produce it.

Both hands are now recorded per file rather than described in prose, so the
question can be asked of the data instead of read out of a paragraph:

| | text | labels |
|---|---|---|
| generated (21) | `tools/generate_cases.py`, by iriguchi | same |
| borrowed (134) | mamori's evaluation corpus, by mamori | `tools/borrow_mamori_cases.py`, by iriguchi |

The borrowed half is the only place those two columns differ, and it differs in
the wrong direction for portability: the *labels* are the hand that could see
these rules. Recorded as `borrowed:mamori`, that was one word for two hands, and
it named the flattering one.

## What installing Presidio buys

Measured 2026-09-04, against presidio-analyzer 2.2 with `en_core_web_lg`, in a
clean venv holding iriguchi and Presidio and nothing else. Reproduce with
`iriguchi --scanner <name> eval`.

| scanner | missed findings | over-caution |
|---|---:|---:|
| `fallback` | 61.7% | 8.9% |
| `presidio` | 44.9% | 35.6% |
| **`fallback+presidio`** | **27.1%** | **41.1%** |

Re-measured on the 197-case corpus. The composite's over-caution fell from 60.8%
to 41.1% when `requests.json` landed, and that is a real result rather than an
improvement to the scanner: the 42 new cases are ordinary work requests with
almost nothing in them to object to, so a detector that over-fires had 42 more
chances to stay quiet. **Over-caution is a rate over the may-leave cases, and
which prompts those are is a property of the corpus.** The entity breakdown below
was taken on the earlier 155 and is kept as recorded.

### Neither scanner dominates the other

This is the finding, and it is the reason `fallback+presidio` exists rather than
a recommendation to switch:

    "Please summarise the memo that Katherine Whitfield sent."
        presidio  ->  presidio.person          fallback  ->  nothing

    "Acme Corporation の田中さんに連絡してください"
        presidio  ->  nothing                  fallback  ->  fallback.japanese-honorific

Presidio has spaCy NER and finds English names the built-in rules were never
going to reach. The built-in rules have a Japanese honorific pattern and
Presidio, running an English model, does not. **A user who read "Presidio is the
better scanner" and selected it would have made their Japanese detection
worse** — 45.2% against 63.5% overall, and strictly worse on the cases the
fallback was written for.

Running both is sound because sensitivity is a **veto** ([ADR-0003](adr/0003-sensitivity-is-a-veto.md)):
findings remove destinations and never add one, so a union is at least as
restrictive as either member. There is no combination rule to get wrong, no
weight to tune, and no way for two scanners to disagree.

### The over-caution is the price, and it is not tuned away

60.8% of may-leave prompts are held back by the composite, against 15.7% for the
fallback alone. Where it comes from, over the 51 may-leave cases:

| entity | cases it fires on | |
|---|---:|---:|
| `DATE_TIME` | 14 | 27.5% |
| `PERSON` | 6 | 11.8% |
| `LOCATION` | 4 | 7.8% |
| `URL` | 3 | 5.9% |
| `IP_ADDRESS`, `NRP` | 1 each | 2.0% |

`DATE_TIME` is the obvious thing to remove — *"by Friday"* is not a reason to
keep a prompt off the network. So it was removed, and measured:

| entities | missed findings | over-caution |
|---|---:|---:|
| every one Presidio supports | **27.9%** | 60.8% |
| minus `DATE_TIME` | 32.7% | 41.2% |
| minus `DATE_TIME`, `URL` | 37.5% | 37.3% |
| minus `DATE_TIME`, `URL`, `LOCATION`, `NRP` | 44.2% | 27.5% |

**Dropping `DATE_TIME` costs 4.8 points of coverage.** Some must-stay-local
cases are caught by nothing else — a date of birth is a date. Every row is a
real trade and none of them is free.

So the default is every entity, which is the fail-closed one, and `entities=`
exists for somebody who has read this table. Picking a row here on the user's
behalf would be iriguchi deciding how much detection their prompts are worth.

### What this does not say

The corpus is 155 cases, 134 of them borrowed from mamori's PII samples. It is a
good test of a *detector* and, as [`feasibility.md`](feasibility.md) F1 records,
no test at all of the complexity axis. These numbers describe Presidio on
**these** prompts, most of which are short strings built to contain personal
data, which is the shape Presidio is strongest on. A miss rate on somebody's
real work is not this number.

## What the cascade's judge actually catches

Measured 2026-09-05 against a live ollama on this machine, over the 42
`requests` prompts. Reproduce with `python tools/measure_cascade.py --model
<name> [--judge consistency]`. It calls a model, so it never runs in CI.

**The prompts and the band labels are ours; the answers are not.** That is what
makes this different from the estimator's 42.9%, which is scored entirely
against material this project wrote.

### The rules judge does nothing

| model | judged weak | signals that fired |
|---|---:|---|
| `qwen2.5:7b-instruct-q4_K_M` | **0 of 42** | `repetition` ×5, `truncated` ×2 |
| `qwen2.5:14b-instruct` | **0 of 42** | `repetition` ×1 |

Not a single escalation, at either size. The `repetition` count moving 5 → 1
between the small and large model is real signal in the right direction, and it
never crossed the threshold.

**This is the trade the registry entry stated before anything was run**: a
confident wrong answer looks exactly like a confident right one, and an
instruct-tuned model does not say *I don't know* to an ordinary work request.
Every rule over the answer text was reading the wrong surface.

Lowering the threshold until it fired would have been fitting a number to a
wish, and the cost of a false *weak* is a prompt sent off the machine.

### Asking twice does separate them

Sampling the same prompt twice at temperature 1.0 and measuring agreement:

| labelled band | median agreement |
|---|---:|
| `low` | **0.435** |
| `moderate` | 0.088 |
| `high` | 0.101 |

A **4.3×** separation between easy and not-easy. It does not distinguish
`moderate` from `high` — those are the same number — and does not need to: the
cascade asks *escalate or not*.

### The threshold came from the curve, not from taste

Agreement was recorded per case, and the escalation rate computed at each cut:

| threshold | low | moderate | high | all |
|---|---:|---:|---:|---:|
| 0.05 | 0% | 7% | 23% | 10% |
| **0.10** | **0%** | **57%** | **62%** | **38%** |
| 0.15 | 27% | 57% | 92% | 57% |
| 0.25 | 40% | 86% | 100% | 74% |

The rule is **the highest threshold at which no `low` prompt escalates**, which
picks 0.10 — not 0.15, which separates the bands six points better and sends 27%
of the easy prompts off the machine to do it.

Re-run at that default, end to end:

| band | judged weak |
|---|---:|
| `low` | **0 of 15 — 0%** |
| `moderate` | 5 of 14 — 36% |
| `high` | 10 of 13 — **77%** |

### What these numbers are not

**A sample, not a constant.** The judge is non-deterministic by construction, and
re-running the whole measurement moves these figures by several points — the two
runs above at threshold 0.10 gave 57%/62% and 36%/77% for moderate/high. The
direction is stable; the digits are not.

**One model, 42 prompts, one machine.** And still no evidence about *correctness*:
every signal here is about confidence, and a model can be consistently wrong.

## What this is not measured against

RouterBench (405k precomputed inferences, 11 models across 7 tasks) and
LLMRouterBench (400k+ instances, 21 datasets, 33 models, January 2026) measure
**cost against quality**: given a query, which model is the cheapest that answers
it well enough.

iriguchi measures whether **sensitivity correctly removes a destination**. These
are not the same problem, and a reader who knows the routing literature will
assume they are. The README says so — *"not an optimiser that happens to be
careful"* — and this document is where the comparison would actually be
attempted, so it says so here too.

One half of it *is* comparable, and separating them is what would make that
honest. The complexity estimate **after** the veto — local or escalate, on a
prompt allowed to go either way — is exactly what those benchmarks measure. The
report does not currently split the two stages, and it should before any
comparison is drawn: `band accuracy` today mixes prompts where the choice was
real with prompts where sensitivity had already settled it.

## What these numbers do not say

- One machine, one OS, two interpreter builds. Linux and macOS will differ,
  probably downward, and probably not by an order of magnitude on memory.
- Working set is not private commit, and Windows reports it generously. This is
  enough to reject a 10 MB target. It is **not** enough to set the replacement
  ceiling, which is why ADR-0008 defers that to v0.3 rather than guessing now.
- Nothing here measures the **warm** path — hotkey pressed to input box visible
  on an already-resident process — which is the number ADR-0008 makes the
  invariant. That measurement does not exist yet because the resident process
  does not exist yet.
- The entropy table is twelve hand-picked tokens, not a corpus. It says the
  thresholds separate *these* twelve, which is enough to choose a starting value
  and not enough to claim a false-positive rate. The number that would be a
  claim is the over-caution rate on the evaluation corpus, and that measurement
  does not exist yet.
- **No part of the corpus is independent of what it scores.** The 21 generated
  cases were written by iriguchi's author using iriguchi's rules; the 134
  borrowed ones by a sibling that can read those rules. Every figure here is a
  regression floor rather than a measured property of the world. See the
  correction above.
- The corpus is 155 cases, generated from templates and borrowed from a sibling.
  It says whether the rules do what the rules intend, **not** whether real
  prompts look like the templates, and it cannot tell you the miss rate on a
  stranger's actual work. Nothing in it substitutes for mamori's own detection
  numbers.
- The band labels on the 134 borrowed cases are rule-assigned, not judged, so
  they say nothing about band accuracy. Read that figure against the 21
  generated cases, where it is 81.0%.
- The mamori comparison is scored largely on mamori's own corpus. See the
  paragraph under that table; the 1.0% is a home-ground figure.
- Nothing here measures the escalation path, because there is no escalation
  path. `ESCALATED` is a verdict with no protection behind it until
  `mamori.protection-scope/1` is implemented and the channel is built.
- The startup and memory figures do not measure iriguchi. They are the floor
  underneath it.

## The probes

- `tools/measure_memory.py` — `K32GetProcessMemoryInfo`, `WorkingSetSize`, three
  stages. Windows only, deliberately: it is the platform these numbers are from,
  and a cross-platform abstraction would hide which one you are reading.
- `tools/measure_startup.py` — subprocess round trip, seven runs, min and median.
- `tools/measure_entropy.py` — Shannon entropy and the rule's verdict, over
  twelve invented tokens.
- `tools/generate_cases.py` — the 21 adversarial cases, deterministically.
- `tools/borrow_mamori_cases.py` — the 134 borrowed ones, run once and committed.

Both are committed, because a measurement whose script is not committed is an
anecdote.
