# iriguchi (入口)

**A local governance router for generative AI.** It stands between you and every
model you use, and decides — locally, deterministically, before a single byte
leaves your machine — where each prompt is allowed to go.

> **v0.1 is built and headless.** The router, the CLI, and a labelled corpus that
> scores it — no GUI, no network, no model. The output below is real. See
> [docs/README.md](docs/README.md) for what is not built yet.

---

## The problem

Two of them, and they are the same problem seen from either side.

**Everything goes to the cloud.** Proofreading a sentence, classifying a row,
translating a phrase — tasks a 3-billion-parameter model on your own laptop
would answer perfectly well — are sent to a datacentre, billed per token, and
retained under someone else's policy.

**Including the things that should not.** The same pipe carries the client
matter, the patient note, the unreleased design. Not because anyone decided it
should, but because there was one pipe and no gate in front of it.

iriguchi is the gate. It is not an optimiser that happens to be careful; it is a
governance boundary that happens to save money.

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

## What makes it different

**The decision is made before the request, from the text alone, by rules you can
read.** No model call in the deciding path. No learned weights. No embedding of
your prompt sent anywhere to decide where your prompt should be sent. The whole
router can be read by a security reviewer in an afternoon
([ADR-0004](docs/adr/0004-decide-before-the-request.md)).

**Sensitivity is a veto, not a score.** It removes destinations, and no
difficulty signal can restore one it removed. "Route this to the big model
because it is hard" is unrepresentable when the prompt contains a credential —
not discouraged, unrepresentable
([ADR-0003](docs/adr/0003-sensitivity-is-a-veto.md)).

**Fail closed.** Doubt routes local. A prompt that must stay local, on a machine
with no local model, is refused — it does not fall through to the network. A
fallback that "helpfully" reaches out when the local model is missing converts
every outage into a leak ([ADR-0002](docs/adr/0002-fail-closed.md)).

**It tells you why, and why not.** Every decision names the rules that fired and
the spans they fired on — and the destinations that were removed, with their
reasons. Never the matched values themselves
([ADR-0006](docs/adr/0006-every-decision-carries-its-reasons.md)).

**Zero runtime dependencies.** A tool that sees every prompt you type is a tool
whose dependency list is a threat model. There isn't one, and CI checks that by
installing the wheel with no extras and asserting nothing came along
([ADR-0001](docs/adr/0001-the-domain-depends-on-nothing.md)). That is a promise
about the **Python** dependency graph: nothing arrives alongside iriguchi, on
any platform. It is not a claim that your platform already has every part of the
standard library — `tkinter` is a separate OS package on most Linux
distributions, and v0.3's tray will say so rather than fail as a broken install
([ADR-0015](docs/adr/0015-what-zero-runtime-dependencies-promises.md)).

## What it does

Three prompts, and the same two axes deciding all of them.

```console
$ iriguchi --local --external route "この記事を三行で要約してください。"

  route        LOCAL      nothing leaves this machine
  sensitivity  clear
  complexity   low

  reasons
    policy.prefer-local
        complexity band low does not call for the larger model, and a local model is permitted

  removed      nothing
  sent         nothing
```

Harder, and nothing sensitive in it, so it may go:

```console
$ iriguchi --local --external route "この二つのアルゴリズムを比較して、計算量を証明してください。"

  route        EXTERNAL   via mamori, protected on the way out
  sensitivity  clear
  complexity   high   (2 signals)  (two escalating markers)

  reasons
    policy.escalate-on-band
        complexity band high and the external destination is permitted

  removed      nothing
  sent         nothing
```

The same difficulty, one address added. **This is the whole point:**

```console
$ iriguchi --local --external route "この二つを比較して証明してください。連絡先は tanaka@example.com です。"

  route        LOCAL      nothing leaves this machine
  sensitivity  restricted   (1 finding)
  complexity   high   (3 signals)  (two escalating markers)

  reasons
    policy.prefer-local
        complexity band high would have called for the larger model, but the external
        destination is not available

  removed
    external     restricted: 1 finding(s), the first from fallback.email-shape at 23-41;
                 not permitted to leave
  sent         nothing
```

The band is still `high`. It makes no difference, because the destination was
removed before difficulty was consulted, and there is no score in this system
that difficulty could have out-voted. Note also that the reason names a *span*,
`23-41`, and never the address.

## What actually leaves

With mamori installed, an outbound route can show you the text that would arrive
— having sent nothing:

```console
$ iriguchi --local --external route --explain --dry-run     "田中と二つのアルゴリズムを比較して、計算量を証明してください。"

  route        EXTERNAL   via mamori, protected on the way out
  ...
  would leave
    <PERSON_001>と二つのアルゴリズムを比較して、計算量を証明してください。

  and the scanner had missed
    mamori-channel.protected-person   mamori protected 1 PERSON value(s) on the
    way out, which the routing decision did not know about — the scanner that
    cleared this prompt missed them.
```

That last section is the seam doing something neither library does alone. The
built-in scanner **cannot find a name without an honorific** — its own largest
documented gap — so it cleared this prompt and the router sent it. mamori caught
the name on the way out, and the person is told the decision was made on less
than the whole picture.

Every refusal on that path leaves the prompt where it is. There is no
configuration in which iriguchi sends something less protected instead
([ADR-0013](docs/adr/0013-iriguchi-reads-a-protection-record-and-keeps-none.md)).

## What it scores

```console
$ iriguchi --local --external eval

cases                155
missed findings       63.5%   <- the scanner's coverage; read this first
leak rate              0.0%   <- end to end, floor of zero, flattered by easy prompts
over-caution rate     15.7%
route accuracy        98.7%
band accuracy         96.1%
decision latency       0.10 ms median
```

**Read the first number, and read it as a recommendation to install mamori.**
The built-in scanner is deliberately dumb (ADR-0005) and cannot find a name
without an honorific, an English name, a company name or an address. It misses
63.5% of the corpus's must-stay-local cases, and that is published rather than
fixed by widening it until the number looks better.

The 0% leak rate underneath it is honest and nearly meaningless on its own —
those prompts are easy, so the *complexity* axis kept them local, and a missed
finding that never became a route is invisible end to end. The first version of
this report had only the second number.

And every figure here is a **regression floor, not a measurement of the world**:
the corpus was written by iriguchi's author and borrowed from a sibling that can
read iriguchi's rules, so none of it is independent of what it scores.
[docs/measurements.md](docs/measurements.md) has the whole story, including what
would have to exist for these numbers to be portable.

## The family

Four local-first libraries, each answering one question, none depending on
another.

| | Question |
|---|---|
| [mamori](https://github.com/Nananananana/mamori) (守) | What in this text is sensitive? |
| [tsumugi](https://github.com/Nananananana/tsumugi) (紡) | What evidence bears on this question? |
| [akashi](https://github.com/Nananananana/akashi) (証) | Did the answer stay inside its evidence? |
| **iriguchi** (入口) | **Where is this prompt allowed to go, and who decided?** |

iriguchi does not reimplement any of them. Detection is a port and mamori is its
adapter ([ADR-0005](docs/adr/0005-detection-is-a-port.md)); tsumugi's evidence
arrives as a published JSON contract that iriguchi reads and never imports
([ADR-0009](docs/adr/0009-tsumugi-is-read-as-json.md)).

## The road

A name in this table is a plan, not a command. `iriguchi ask` reads like
something you could type, and it is not — the built commands are `route`,
`config`, `doctor`, `demo` and `eval`, and `iriguchi --help` is the authority.

| | | |
|---|---|---|
| **v0.1** | **built** | The router, headless. Domain, ports, fallback scanner, complexity estimator, CLI, evaluation corpus. No GUI, no network, no model. |
| **v0.2** | **built** | mamori as the scanner (`--scanner mamori`), and as the escalation channel. |
| **v0.2** | *not built* | ollama as the local model; `iriguchi ask`, which would be the first command that actually sends. |
| **v0.3** | *not built* | The shell. Tray residency, hotkey, popup — with measured performance floors on the warm path. |
| **v0.4** | *not built* | The Anchor Dashboard. Provenance from tsumugi and akashi, rendered — including what was left out. |
| **v1.0** | *not built* | Full-offline routing. No new intelligence. |

[docs/proposals/0001-the-design.md](docs/proposals/0001-the-design.md) is the
whole design, including the parts of the original specification it revises and
why.

## On performance

The original specification asked for 10 MB resident and 1 ms startup. Both were
measured before they were promised, and neither is reachable: a CPython process
that has imported nothing is already 12.8 MB, and creating it costs 32 ms at
best — and anywhere up to twenty times that when the machine is busy
([docs/measurements.md](docs/measurements.md)).

So the invariant is the **warm path** — hotkey pressed to input box visible, on
an already-resident process — because that is what a person actually experiences
and it is what a build can honestly gate on
([ADR-0008](docs/adr/0008-the-invariant-is-the-warm-path.md)).

Every number in this repository is measured, ships with the script that produced
it, and states what it does not say.

## Trying it

```bash
uv pip install -e ".[dev]" && iriguchi --local --external demo
```

Both destinations default to **off**, which is the fail-safe value: a person who
has configured nothing gets refusals rather than a router quietly assuming a
model exists. `iriguchi doctor` says what is missing and what its absence costs.

## Licence

Apache-2.0.
