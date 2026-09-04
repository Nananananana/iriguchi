"""What a policy change would do, before it does it.

    python tools/simulate.py --high-at 0.5
    python tools/simulate.py --scanner fallback+presidio
    python tools/simulate.py --marker-weight complexity.multi-step=0.8 --show-changed

The review asked for this twice -- *policy simulation: measure the effect of a
policy change without sending anything* -- and it is the question an operator
actually has. Not *what is the accuracy*, which is a number about a corpus, but
**which prompts move, and in which direction, if I change this**.

The direction is the part that matters and the part a single accuracy figure
hides. Two settings can move the same number of prompts and be opposites: one
sends work outward, the other keeps it home. A change that improves accuracy by
moving four prompts outward is not the same change as one that improves it by
four inward, and only one of those is a leak risk.

So the report is a confusion matrix over routes, and the counts that get their
own line are the ones that cross the boundary this project exists to guard:

    became external   a prompt that used to stay home now leaves
    became local      the reverse
    became refused    the change made something unanswerable

## What it cannot tell you

The corpus is 155 cases, 134 of them borrowed from a PII detector's samples with
a median length of 34 characters. `docs/feasibility.md` F1 records what that
means: it exercises the veto well and the complexity axis barely at all. A
simulation over it describes **these** prompts. Run it against your own corpus
with `--corpus` before trusting a number to describe your traffic.

Nothing here calls a model or opens a socket. That is the whole point: a policy
change can be measured before anyone's prompt is affected by it.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.complexity import Thresholds
from iriguchi.domain.destination import Destination
from iriguchi.errors import ConfigurationError, IriguchiError
from iriguchi.evaluation.case import Case
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.infrastructure.estimators.rules import RulesEstimator, RulesSettings
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})

#: The crossings that get their own line. Ordered by how much somebody should
#: care: a prompt that started leaving is the one worth waking up for.
NOTABLE = (
    ("local", "external", "began leaving the machine"),
    ("refused", "external", "began leaving the machine"),
    ("external", "local", "stopped leaving"),
    ("external", "refused", "stopped leaving"),
    ("local", "refused", "became unanswerable"),
    ("refused", "local", "became answerable"),
)


@dataclass(frozen=True, slots=True)
class Setup:
    """One configuration to route the corpus under."""

    scanner: str
    estimator: str
    thresholds: Thresholds
    settings: RulesSettings

    def router(self) -> PromptRouter:
        estimator = (
            RulesEstimator(self.settings)
            if self.estimator == "rules"
            else ESTIMATORS.build(self.estimator)
        )
        return PromptRouter(
            scanner=SCANNERS.build(self.scanner),
            estimator=estimator,
            thresholds=self.thresholds,
        )

    def describe(self) -> str:
        parts = [f"scanner {self.scanner}", f"estimator {self.estimator}"]
        if self.thresholds != Thresholds():
            parts.append(
                f"bands {self.thresholds.moderate_at:g}/{self.thresholds.high_at:g}"
                f"@{self.thresholds.short_circuit_at}"
            )
        if self.settings != RulesSettings():
            moved = [
                f"{name}={getattr(self.settings, name)!r}"
                for name in self.settings.__dataclass_fields__
                if getattr(self.settings, name) != getattr(RulesSettings(), name)
            ]
            parts.extend(moved)
        return ", ".join(parts)


def routes(setup: Setup, cases: tuple[Case, ...]) -> dict[str, str]:
    """Every case's route under `setup`, by case id."""
    router = setup.router()
    return {case.id: router.route(case.prompt, BOTH).route.value for case in cases}


def _weights(pairs: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for pair in pairs:
        rule, _, value = pair.partition("=")
        if not value:
            raise SystemExit(f"--marker-weight wants rule=weight, got {pair!r}")
        try:
            out[rule] = float(value)
        except ValueError:
            raise SystemExit(f"{value!r} is not a number") from None
    return out


def build_parser() -> argparse.ArgumentParser:
    """The flags, as their own function.

    Separated from `main` so anything that needs to know what this tool accepts
    can ask rather than reproduce it -- the README test checks that every flag
    the README documents is real, and it documents two programs now.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scanner", default=None, choices=SCANNERS.names)
    parser.add_argument("--estimator", default=None, choices=ESTIMATORS.names)
    parser.add_argument("--moderate-at", type=float, default=None)
    parser.add_argument("--high-at", type=float, default=None)
    parser.add_argument("--short-circuit-at", type=int, default=None)
    parser.add_argument("--long-input-at", type=int, default=None)
    parser.add_argument(
        "--marker-weight",
        action="append",
        default=[],
        metavar="RULE=WEIGHT",
        help="retune one rule, repeatable",
    )
    parser.add_argument(
        "--corpus", type=Path, help="a directory of case files; defaults to the shipped one"
    )
    parser.add_argument("--show-changed", action="store_true", help="list the cases that moved")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cases = load_corpus(args.corpus)
    except (OSError, ValueError) as failure:
        print(f"could not load the corpus: {failure}", file=sys.stderr)
        return 1
    if not cases:
        print("the corpus is empty, so a simulation would be about nothing", file=sys.stderr)
        return 1

    baseline = Setup("fallback", "rules", Thresholds(), RulesSettings())
    try:
        proposed = Setup(
            scanner=args.scanner or baseline.scanner,
            estimator=args.estimator or baseline.estimator,
            thresholds=Thresholds(
                moderate_at=(
                    baseline.thresholds.moderate_at
                    if args.moderate_at is None
                    else args.moderate_at
                ),
                high_at=baseline.thresholds.high_at if args.high_at is None else args.high_at,
                short_circuit_at=(
                    baseline.thresholds.short_circuit_at
                    if args.short_circuit_at is None
                    else args.short_circuit_at
                ),
            ),
            settings=RulesSettings(
                long_input_at=(
                    baseline.settings.long_input_at
                    if args.long_input_at is None
                    else args.long_input_at
                ),
                marker_weights=_weights(args.marker_weight),
            ),
        )
    except ConfigurationError as refused:
        print(f"the proposed policy is not one iriguchi can hold: {refused}", file=sys.stderr)
        return 1

    if proposed == baseline:
        print(
            "nothing was proposed, so nothing would change. Pass a setting to "
            "simulate -- `--help` lists them.",
            file=sys.stderr,
        )
        return 1

    try:
        before, after = routes(baseline, cases), routes(proposed, cases)
    except IriguchiError as failure:
        print(f"the simulation could not run: {failure}", file=sys.stderr)
        return 1

    print(f"corpus  {len(cases)} cases")
    print(f"from    {baseline.describe()}")
    print(f"to      {proposed.describe()}\n")

    moved = {
        case_id: (before[case_id], after[case_id])
        for case_id in before
        if before[case_id] != after[case_id]
    }
    share = 100 * len(moved) / len(cases)
    print(f"  {len(moved)} of {len(cases)} prompts change route ({share:.1f}%)\n")

    crossings = Counter(moved.values())
    for source, target, meaning in NOTABLE:
        count = crossings.get((source, target), 0)
        if count:
            print(f"    {source:8} -> {target:8}  {count:4}   {meaning}")
    unnamed = {
        pair: n
        for pair, n in crossings.items()
        if (pair[0], pair[1]) not in {(s, t) for s, t, _ in NOTABLE}
    }
    for (source, target), count in sorted(unnamed.items()):
        print(f"    {source:8} -> {target:8}  {count:4}")

    outward = sum(n for (s, t), n in crossings.items() if t == "external" and s != "external")
    if outward:
        print(
            f"\n  {outward} prompt(s) that did not leave this machine now would. "
            f"That is the\n  direction to be sure about, and no accuracy figure "
            f"would have shown it."
        )
    elif moved:
        print("\n  Nothing began leaving the machine under this change.")

    if args.show_changed:
        print("\n  changed cases")
        for case_id, (source, target) in sorted(moved.items()):
            print(f"    {case_id:34} {source:8} -> {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
