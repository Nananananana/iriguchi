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
| the veto removed external | 46 | 29.7% |
| complexity kept it local | 107 | 69.0% |
| **complexity sent it out** | **2** | **1.3%** |

Split by where the case came from:

| source | n | veto | local | external | median length |
|---|---:|---:|---:|---:|---:|
| `borrowed:mamori` | 134 | 37 | 97 | **0** | 34 chars |
| `generated` | 21 | 9 | 10 | 2 | 44 chars |

**The borrowed 134 cannot exercise the axis at all**, and the reason is visible
in one number: their median length is **34 characters** and their longest is 85.
They are mamori's PII samples — a name, a particle, an email address. A
complexity estimator reading `田中さんに tanaka@example.com で連絡` has nothing
to estimate, because that is not a request for work. It is a string containing
personal data, which is what it was written to be.

So 86% of the corpus is on loan from a project measuring a different thing, and
it measures the veto well because the veto is what it was built for.

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

**Fixed.** Four states rather than three, protection reported before the
endpoint, because an endpoint is two environment variables away and mamori is
not on PyPI. `doctor` now prints:

    external service  cannot be used  nothing here can protect an outbound prompt

with a paragraph saying that `route` will still say a prompt may leave while
`ask --external` refuses, which is the disagreement somebody would otherwise
meet at the moment of sending.

---

## F4. The default scanner's documented remedy is the uninstallable package

`missed findings` is **63.5%** (66 of 104 must-stay-local cases), and
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
