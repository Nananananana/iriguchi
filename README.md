# iriguchi (入口)

**A local governance router for generative AI.** It stands between you and every
model you use, and decides — locally, deterministically, before a single byte
leaves your machine — where each prompt is allowed to go.

> **Nothing is built yet.** This repository currently holds the design, the ten
> decisions it rests on, and the measurements that forced two of them. See
> [docs/README.md](docs/README.md) for where the project actually is. Everything
> below describes what is being built, not what you can install.

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
([ADR-0001](docs/adr/0001-the-domain-depends-on-nothing.md)).

## What it will look like

```console
$ iriguchi route --explain --dry-run "Summarise the attached meeting notes"

  route      LOCAL
  sensitivity  clear          (no scanner finding)
  complexity   low            summarise + 34 tokens

  reasons
    complexity.short-input          length 34 < 200
    complexity.single-step          no multi-step marker

  removed    nothing
  sent       nothing
```

```console
$ iriguchi route --explain --dry-run "Draft a reply to tanaka@example.com about the Q3 numbers"

  route      LOCAL
  sensitivity  restricted     (1 finding)
  complexity   medium

  reasons
    fallback.email-shape            span 20-38     [value withheld]

  removed    EXTERNAL       a finding at 20-38 is not permitted to leave
  sent       nothing

  note: the built-in fallback scanner over-detects on purpose. Install
        mamori alongside it for a scanner that can tell a real finding
        from a shape.
```

Nothing above runs yet. It is here so that the interface is designed before it
is implemented, and so that the promises are concrete enough to be wrong.

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

| | |
|---|---|
| **v0.1** | The router, headless. Domain, ports, fallback scanner, complexity estimator, CLI, evaluation corpus. No GUI, no network, no model. |
| **v0.2** | The seams. mamori as scanner and as escalation channel; ollama as the local model; `iriguchi ask`. |
| **v0.3** | The shell. Tray residency, hotkey, popup — with measured performance floors on the warm path. |
| **v0.4** | The Anchor Dashboard. Provenance from tsumugi and akashi, rendered — including what was left out. |
| **v1.0** | Full-offline routing. No new intelligence. |

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

## Licence

Apache-2.0.
