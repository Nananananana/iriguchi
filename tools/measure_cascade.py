"""Does the judge fire when a small model actually struggles?

    python tools/measure_cascade.py --model qwen2.5:7b-instruct-q4_K_M
    python tools/measure_cascade.py --model MODEL --against BIGGER

**This is the measurement the other axis cannot have.** `docs/feasibility.md` F1
records the complexity estimator at 42.9% and attaches the honest caveat: the 42
prompts were written by the same hand that writes the rules, so the number
diagnoses and does not validate.

The judge does not have that problem in the same way. It is scored against
**answers a real model produced**, which nobody here wrote. The prompts are still
ours and the band labels are still ours, but the artefact being judged is not,
and that is the part that matters: the question *did this model produce something
poor* has an answer that exists independently of anybody's opinion about it.

## What a good result looks like

The cascade's premise is that a small model struggles more on prompts labelled
`high` than on prompts labelled `low`. So the judge should fire more often on
the hard ones. If it fires at the same rate everywhere it is measuring
*something* -- verbosity, formatting, a model's habits -- but not difficulty, and
the cascade would be escalating at random.

The report is therefore a rate **per labelled band**, not an accuracy. There is
no ground truth for "was this answer good"; there is only whether the judge's
opinion tracks the thing the cascade needs it to track.

`--against` runs a second, larger model over the same prompts. If the judge is
measuring difficulty rather than style, it should fire **less** on the larger
model's answers -- and that comparison needs no labels at all, which makes it the
strongest evidence available here.

## What it cannot tell you

Whether an answer was *wrong*. Every signal here is about the shape of the text
or about the model declining, and a confident wrong answer looks exactly like a
confident right one. That is stated in the judge's registry entry as the trade it
makes, and no amount of running it changes it.

This calls a model, so it lives in `tools/` and never runs in CI (ADR-0007).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iriguchi.domain.answer import AnswerQuality
from iriguchi.errors import ModelError
from iriguchi.evaluation.case import Case
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.infrastructure.judges.consistency import ConsistencyJudge
from iriguchi.infrastructure.judges.rules import RulesJudge
from iriguchi.infrastructure.models.openai_compatible import OpenAICompatibleModel

BANDS = ("low", "moderate", "high")


def _cases(source: str) -> tuple[Case, ...]:
    return tuple(case for case in load_corpus() if case.source == source)


def run(
    model: OpenAICompatibleModel,
    cases: tuple[Case, ...],
    judge: RulesJudge | ConsistencyJudge,
) -> dict[str, list[Any]]:
    """Ask, judge, and keep what happened. Failures are recorded, not dropped."""
    rows: dict[str, list[Any]] = {"band": [], "weak": [], "rules": [], "seconds": [], "failed": []}
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        try:
            answer = model.answer(case.prompt)
            failed = False
        except ModelError as failure:
            print(f"  [{index}/{len(cases)}] {case.id}: {failure}", file=sys.stderr)
            answer, failed = "", True
        elapsed = time.perf_counter() - started
        quality = AnswerQuality.from_signals(judge.judge(case.prompt, answer))
        rows["band"].append(case.band.value)
        rows["weak"].append(quality.is_weak)
        rows["rules"].append(tuple(s.rule for s in quality.signals))
        rows["seconds"].append(elapsed)
        rows["failed"].append(failed)
        print(
            f"  [{index}/{len(cases)}] {case.band.value:8} "
            f"{'WEAK' if quality.is_weak else 'ok  '} {elapsed:5.1f}s  {case.id}",
            file=sys.stderr,
        )
    return rows


def report(name: str, rows: dict[str, list[Any]], out: TextIO) -> dict[str, float]:
    """Fire rate per labelled band, plus what fired."""
    total = len(rows["band"])
    failures = sum(rows["failed"])
    print(f"\n{name}", file=out)
    if failures:
        print(
            f"  {failures} of {total} calls failed and are counted as weak, "
            f"because a model that did not answer did not answer",
            file=out,
        )
    print(f"  answered in {statistics.median(rows['seconds']):.1f}s median", file=out)

    rates: dict[str, float] = {}
    print(f"\n  {'band':10}{'n':>5}{'judged weak':>14}", file=out)
    for band in BANDS:
        indexes = [i for i, b in enumerate(rows["band"]) if b == band]
        if not indexes:
            continue
        weak = sum(1 for i in indexes if rows["weak"][i])
        rates[band] = 100 * weak / len(indexes)
        print(f"  {band:10}{len(indexes):>5}{weak:>7} = {rates[band]:5.1f}%", file=out)

    overall = 100 * sum(rows["weak"]) / total
    rates["all"] = overall
    print(f"  {'all':10}{total:>5}{sum(rows['weak']):>7} = {overall:5.1f}%", file=out)

    fired = Counter(rule for rules in rows["rules"] for rule in rules)
    if fired:
        print("\n  which signals fired", file=out)
        for rule, count in fired.most_common():
            print(f"    {rule:34}{count:>5}", file=out)
    return rates


def verdict(rates: dict[str, float], out: TextIO) -> None:
    """The one sentence this tool exists to produce."""
    if "high" not in rates or "low" not in rates:
        return
    gap = rates["high"] - rates["low"]
    print(f"\n  high minus low: {gap:+.1f} points", file=out)
    if gap > 0:
        print(
            "  The judge fires more on the prompts labelled hard, which is what a\n"
            "  cascade needs it to do. It is not a large sample and it is one model.",
            file=out,
        )
    else:
        print(
            "  **The judge does not fire more on the hard prompts.** It is measuring\n"
            "  something -- verbosity, formatting, this model's habits -- but not\n"
            "  difficulty, and a cascade built on it would escalate at random.",
            file=out,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="the small local model to test")
    parser.add_argument("--against", help="a larger model to compare with, over the same prompts")
    parser.add_argument("--url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--source", default="requests", help="which corpus source to use")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument(
        "--judge",
        default="rules",
        choices=("rules", "consistency"),
        help="consistency re-asks the local model and compares, at one extra call",
    )
    args = parser.parse_args(argv)

    cases = _cases(args.source)
    if not cases:
        print(f"no cases from source {args.source!r}", file=sys.stderr)
        return 1

    small = OpenAICompatibleModel(args.url, args.model, temperature=args.temperature)
    judge: RulesJudge | ConsistencyJudge = (
        RulesJudge()
        if args.judge == "rules"
        else ConsistencyJudge(OpenAICompatibleModel(args.url, args.model, temperature=1.0))
    )
    print(
        f"{len(cases)} prompts from {args.source!r}, judged by {judge.name!r}.\n"
        f"Prompts and band labels are this project's; the answers are not, which\n"
        f"is the half that makes this worth running.\n"
    )

    rates = report(f"{args.model}  (the small one)", run(small, cases, judge), sys.stdout)
    verdict(rates, sys.stdout)

    if args.against:
        large = OpenAICompatibleModel(args.url, args.against, temperature=args.temperature)
        bigger = report(f"{args.against}  (the larger one)", run(large, cases, judge), sys.stdout)
        moved = rates["all"] - bigger["all"]
        print(
            f"\n  the larger model is judged weak {moved:+.1f} points less often", file=sys.stdout
        )
        if moved > 0:
            print(
                "  Which is the cascade's whole premise, and it needs no labels:\n"
                "  the same judge, the same prompts, a better model, fewer objections.",
                file=sys.stdout,
            )
        else:
            print(
                "  **The larger model is not judged better.** Either the judge is\n"
                "  measuring style rather than adequacy, or these prompts do not\n"
                "  separate the two models. Both are findings; neither supports\n"
                "  escalating on this signal.",
                file=sys.stdout,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
