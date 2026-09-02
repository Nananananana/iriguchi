"""What ADR-0004 asserted without a number.

    iriguchi measure-router --model qwen2.5:14b-instruct-q4_K_M

ADR-0004 refuses a model in the deciding path and states the cost as: *the
learned routers are better at the cost-quality trade and will stay better, and
no amount of rule-writing closes that gap.* **That is a claim about a magnitude,
with no magnitude, and about permanence.** This is the tool that puts a number
on the first half.

**It cannot decide anything**, and that is not a limitation to be apologised
for. ADR-0004's reason is auditability, not accuracy: *a router a person cannot
read is a router they cannot trust with the second kind of error.* A large gap
would not move it. What the number does is stop the ADR borrowing the *form* of
evidence for a decision that does not rest on evidence — and it cuts both ways,
which is the half nobody goes looking for:

    gap large   the ADR is right and finally has a figure
    gap small   **the ADR has been overstating what iriguchi gives up**, and the
                rule is cheaper than it has been presented as being

## Why this lives in `tools/` and not in the package

Putting a model-backed estimator in `infrastructure/estimators/` would make it
an adapter somebody can wire, which is the exact thing ADR-0004 refuses. Putting
it in `evaluation/` would break the `no-network` contract, and rightly. A
measurement instrument is not a feature; `tools/measure_memory.py` set the
precedent.

## Read the caveats before the number

They are printed with every run rather than kept in a document, because a figure
that travels without them is a figure that will be quoted without them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from iriguchi.domain.complexity import Complexity  # noqa: E402
from iriguchi.errors import ModelError  # noqa: E402
from iriguchi.infrastructure.estimators.rules import RulesEstimator  # noqa: E402
from iriguchi.infrastructure.models.openai_compatible import OpenAICompatibleModel  # noqa: E402

BANDS = ("low", "moderate", "high")

#: The corpus this measures. **Only this one.** The 134 borrowed cases all carry
#: `band: low`, assigned by `tools/borrow_mamori_cases.py` from these same rules,
#: and their own file says they say nothing about band accuracy. Including them
#: would inflate every figure here by 134 free agreements with the thing being
#: tested.
CORPUS = ROOT / "src" / "iriguchi" / "evaluation" / "data" / "generated.json"


class Outcome(Enum):
    """Why a case produced no band, kept apart rather than scored as wrong.

    bench found four of these collapsed into one boolean in their own
    generator, where they read as "the writer redacted nothing". A model that
    times out, a model that returns nothing, and a model that returns a
    paragraph instead of a word are three different findings about three
    different problems, and only the last is about the model's judgement.
    """

    ANSWERED = "answered"
    EMPTY = "empty"
    UNPARSEABLE = "unparseable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Judgement:
    case_id: str
    label: str
    predicted: str | None
    outcome: Outcome
    raw: str = ""
    seconds: float = 0.0


COLD = """You route prompts between a small local model and a large remote one.

Answer with exactly one word: low, moderate, or high.

low       a small local model will answer this adequately
moderate  a small model will probably manage, but a larger one would answer better
high      this needs the larger model to be answered well

The prompt:
---
{prompt}
---

One word only."""

BRIEFED = """Classify how much model capability this request needs.

Answer with exactly one word: low, moderate, or high.

high      it asks for two or more hard things at once, or asks for code to be
          written or refactored together with an explanation of why, or asks
          for a proof, a comparison of several things, or multi-step reasoning
moderate  one such marker, or a long or structurally involved request
low       everything else, including proofreading, translation, summarising,
          formatting, and short factual questions

The prompt:
---
{prompt}
---

One word only."""

PROMPTS = {"cold": COLD, "briefed": BRIEFED}


def rules_band(prompt: str) -> str:
    """What iriguchi decides today, through the domain rather than around it.

    The estimator returns signals; the band is the domain's, computed by
    `Complexity.from_signals`. Calling the estimator and reading a band off it
    would be measuring something the product does not do.
    """
    return Complexity.from_signals(RulesEstimator().estimate(prompt)).band.value


def parse(reply: str) -> str | None:
    """One of three words, or nothing.

    Permissive about surroundings and strict about content: a model that says
    "moderate." or "**high**" meant a band, and a model that says "it depends"
    did not. Returning `None` rather than guessing is what keeps `UNPARSEABLE`
    separate from a wrong answer.
    """
    lowered = reply.strip().lower()
    found = [band for band in BANDS if band in lowered]
    return found[0] if len(found) == 1 else None


def judge(model: Any, template: str, cases: list[dict[str, Any]]) -> list[Judgement]:
    results: list[Judgement] = []
    for case in cases:
        started = time.monotonic()
        try:
            reply = model.answer(template.format(prompt=case["prompt"]))
        except ModelError as failure:
            results.append(Judgement(case["id"], case["band"], None, Outcome.FAILED, str(failure)))
            continue
        elapsed = time.monotonic() - started
        if not reply.strip():
            results.append(Judgement(case["id"], case["band"], None, Outcome.EMPTY, "", elapsed))
            continue
        band = parse(reply)
        results.append(
            Judgement(
                case["id"],
                case["band"],
                band,
                Outcome.ANSWERED if band else Outcome.UNPARSEABLE,
                reply.strip()[:200],
                elapsed,
            )
        )
    return results


def score(judgements: list[Judgement]) -> dict[str, Any]:
    total = len(judgements)
    answered = [j for j in judgements if j.outcome is Outcome.ANSWERED]
    correct = [j for j in answered if j.predicted == j.label]
    per_class = {
        band: (
            sum(1 for j in correct if j.label == band),
            sum(1 for j in judgements if j.label == band),
        )
        for band in BANDS
    }
    return {
        "n": total,
        # **Over every case, not over the ones that answered.** A model that
        # answers eight of twenty-one and gets all eight right has not scored
        # 100%; it has failed thirteen times in a way that matters more than a
        # wrong band.
        "correct": len(correct),
        "accuracy": len(correct) / total if total else 0.0,
        "outcomes": {o.value: sum(1 for j in judgements if j.outcome is o) for o in Outcome},
        "per_class": per_class,
        "confusion": Counter((j.label, j.predicted or j.outcome.value) for j in judgements),
        "seconds": sum(j.seconds for j in judgements),
    }


def report(name: str, result: dict[str, Any], out: Any) -> None:
    accuracy = 100 * result["accuracy"]
    print(f"\n{name}", file=out)
    print(f"  band accuracy      {result['correct']}/{result['n']} = {accuracy:.1f}%", file=out)
    unusable = {k: v for k, v in result["outcomes"].items() if k != "answered" and v}
    if unusable:
        print(f"  produced no band   {unusable}", file=out)
    parts = " ".join(f"{b} {c}/{t}" for b, (c, t) in result["per_class"].items())
    print(f"  per class          {parts}", file=out)
    if result["seconds"]:
        print(f"  wall               {result['seconds']:.1f}s total", file=out)


def caveats(baseline: float, n: int, model: str, sampling: str) -> str:
    per_case = 100.0 / n
    return f"""
Read these before the numbers, and carry them with any number taken from here.

  1. n = {n}. **One case changing band is {per_case:.2f} points.** A difference
     smaller than about {3 * per_case:.0f} points is three cases and is not a result.
  2. **Always answering "low" scores {baseline:.1f}%.** That is the number every
     figure below has to beat before it means anything at all.
  3. **The labels and the rules come from the same hand.** Both were written
     here. The comparison is therefore biased toward the rules by construction:
     if the rules win it proves little, and if the model wins despite that it is
     the stronger finding.
  4. **One lineage.** bench measured the locally available models and found no
     second family: qwen2.5 usable, llama3.1 0/8 (repetition loops at
     temperature 0), gemma4 1/8 (empty responses). qwen3 and qwen2.5:7b are the
     same lineage.
  5. **Choosing a model that can follow the format chooses for capability**, and
     capability may correlate with the thing being judged. Two of three families
     fell out on format and the survivor was the largest.
  6. Sampling: {sampling}. Model: {model}. **`iriguchi ask` leaves the
     temperature to the server**, so these figures do not describe the setting
     the product runs under.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="the model to ask")
    parser.add_argument("--url", default="http://127.0.0.1:11434/v1")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help=(
            "0 by default, and not because determinism is nice: at n=21 one case "
            "is 4.76 points, so characterising sampling variance would take N runs "
            "of 21 and there is no budget for that in a corpus this size"
        ),
    )
    parser.add_argument("--framing", choices=[*PROMPTS, "both"], default="both")
    parser.add_argument("--json", type=Path, help="also write the raw judgements here")
    args = parser.parse_args(argv)

    cases = json.loads(CORPUS.read_text(encoding="utf-8"))["samples"]
    labels = Counter(c["band"] for c in cases)
    baseline = 100 * labels.most_common(1)[0][1] / len(cases)

    model = OpenAICompatibleModel(args.url, args.model, temperature=args.temperature)
    print(caveats(baseline, len(cases), model.name, model.sampling))

    print(f"always answering {labels.most_common(1)[0][0]!r}")
    print(f"  band accuracy      {labels.most_common(1)[0][1]}/{len(cases)} = {baseline:.1f}%")

    rules = [
        Judgement(c["id"], c["band"], rules_band(c["prompt"]), Outcome.ANSWERED) for c in cases
    ]
    report("the rules (what iriguchi decides today)", score(rules), sys.stdout)

    # `asdict`, not `__dict__`: `slots=True` means there is no instance dict,
    # and the traceback for that arrives after the model has been asked
    # twenty-one times.
    everything: dict[str, Any] = {
        "rules": [{**asdict(j), "outcome": j.outcome.value} for j in rules]
    }
    for framing in PROMPTS if args.framing == "both" else [args.framing]:
        judgements = judge(model, PROMPTS[framing], cases)
        report(f"{args.model}, {framing}", score(judgements), sys.stdout)
        everything[framing] = [{**asdict(j), "outcome": j.outcome.value} for j in judgements]

    if args.json:
        args.json.write_text(
            json.dumps(everything, ensure_ascii=False, indent=2), encoding="utf-8", newline=""
        )
        print(f"\nraw judgements written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
