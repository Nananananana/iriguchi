"""Turning "send 30% to the big model" into the numbers that do it.

    python tools/calibrate.py --escalate 0.3
    python tools/calibrate.py --sweep

`Thresholds` defaults to 0.3 and 0.7 and those are choices somebody made. **An
operator does not have an opinion about 0.7.** They have an opinion about how
much of their traffic is worth the larger model, and about how much they are
willing to spend, and neither of those is a score.

RouteLLM (Apache-2.0, LMSYS) is where this framing is argued properly: a router
is a score plus a **cost threshold α**, calibrated so a chosen fraction of
queries reaches the strong model. Their routers learn the score from preference
data; iriguchi's is rules, by ADR-0004, and **the calibration half transfers
without the learning half.** That is the whole of what is borrowed here.

## What it can and cannot tell you

    can      the threshold that sends `--escalate` of *this corpus* outward
    cannot   whether that is the right fraction for your traffic

The second is not modesty. The corpus is 21 generated cases written here plus
134 borrowed from mamori, and a rate calibrated on it describes those prompts
and no others. The number printed is a **starting point that is honest about
where it came from**, which is more than 0.7 ever was.

## Why the sensitivity axis is not calibrated

Only the complexity threshold moves. Sensitivity is a veto (ADR-0003), and a
veto with a tunable strength is not a veto -- an operator who could dial it down
to hit a cost target would be trading leaks for money, one setting at a time,
which is precisely the trade this project exists to refuse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from iriguchi.domain.complexity import Complexity, Thresholds  # noqa: E402
from iriguchi.domain.destination import Destination  # noqa: E402
from iriguchi.evaluation.dataset import load_corpus  # noqa: E402
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS  # noqa: E402

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})


def scores(prompts: list[str], estimator_name: str) -> list[float]:
    """Every prompt's complexity score, threshold-free.

    The score is what a threshold is applied *to*, so it is computed once and
    the sweep is arithmetic on the result rather than a re-run per candidate.
    """
    estimator = ESTIMATORS.build(estimator_name)
    return [Complexity.from_signals(estimator.estimate(prompt)).score for prompt in prompts]


def outward_rate(
    prompts: list[str], estimator_name: str, scanner_name: str, thresholds: Thresholds
) -> float:
    """The fraction that would actually leave, veto included.

    **Not the fraction scoring above the threshold.** A prompt the scanner
    objects to stays local whatever its band, so a rate computed from scores
    alone would promise an escalation rate the router will not deliver -- and
    the gap is exactly the corpus's sensitive half. Measured through the real
    router rather than modelled.
    """
    from iriguchi.application.routing import PromptRouter

    router = PromptRouter(
        scanner=SCANNERS.build(scanner_name),
        estimator=ESTIMATORS.build(estimator_name),
        thresholds=thresholds,
    )
    outward = sum(1 for p in prompts if router.route(p, BOTH).leaves_the_machine)
    return outward / len(prompts) if prompts else 0.0


def candidates(values: list[float]) -> list[float]:
    """Thresholds worth trying: every score, and just above each.

    A threshold only matters where it crosses a score, so the interesting
    values are the scores themselves -- `>=` makes a score its own boundary --
    plus a hair above each, which is the first threshold that excludes it.
    """
    unique = sorted(set(values))
    stepped = [v + 1e-9 for v in unique]
    return sorted({0.0, *unique, *stepped, 1.0})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--escalate",
        type=float,
        help="target fraction of the corpus that should leave, e.g. 0.3",
    )
    parser.add_argument("--sweep", action="store_true", help="print the whole curve instead")
    parser.add_argument("--estimator", default=ESTIMATORS.default, choices=ESTIMATORS.names)
    parser.add_argument("--scanner", default=SCANNERS.default, choices=SCANNERS.names)
    parser.add_argument("--source", help="only cases from this source")
    args = parser.parse_args(argv)

    if args.escalate is None and not args.sweep:
        parser.error("give --escalate a fraction, or --sweep to see the curve")
    if args.escalate is not None and not 0.0 <= args.escalate <= 1.0:
        parser.error(f"--escalate {args.escalate} is not a fraction")

    cases = [c for c in load_corpus() if args.source is None or c.source == args.source]
    prompts = [case.prompt for case in cases]
    if not prompts:
        print("the corpus selection is empty; there is nothing to calibrate on", file=sys.stderr)
        return 1

    values = scores(prompts, args.estimator)
    default = Thresholds()
    print(f"corpus            {len(prompts)} prompts", end="")
    print(f" from {args.source}" if args.source else " (all sources)")
    print(f"estimator         {args.estimator}     scanner {args.scanner}")
    print(
        f"today             high_at {default.high_at} sends "
        f"{100 * outward_rate(prompts, args.estimator, args.scanner, default):.1f}% outward"
    )

    curve: list[tuple[float, float]] = []
    for candidate in candidates(values):
        # `moderate_at` is pinned below `high_at` because `Thresholds` refuses
        # the inversion, and only the escalation boundary is being calibrated.
        cut = Thresholds(moderate_at=min(default.moderate_at, candidate), high_at=candidate)
        curve.append((candidate, outward_rate(prompts, args.estimator, args.scanner, cut)))

    if args.sweep:
        # `.12g`, because the candidates differ by 1e-9 and six decimals
        # printed two rows as `0.000000` with different rates beside them --
        # a table that looks like it contradicts itself.
        print("\n  high_at          outward")
        last: float | None = None
        for threshold, rate in curve:
            if rate != last:  # only where the curve moves
                print(f"  {threshold:<16.12g} {100 * rate:5.1f}%")
                last = rate
        return 0

    target = float(args.escalate)
    # The lowest threshold whose rate is at or under the target: raising the
    # threshold can only send less, so this is the most escalation the operator
    # asked for without exceeding it. Ties go to the smaller threshold, which
    # keeps the choice reproducible.
    at_or_under = [(t, r) for t, r in curve if r <= target]
    if not at_or_under:
        print(f"\nno threshold reaches {100 * target:.0f}% or less on this corpus.")
        return 1
    chosen, achieved = min(at_or_under, key=lambda pair: (abs(pair[1] - target), pair[0]))

    print(f"\ntarget            {100 * target:.0f}% outward")
    print(f"closest reachable {100 * achieved:.1f}%  at high_at {chosen:.12g}")
    print(f"\n  export IRIGUCHI_HIGH_AT={chosen:.12g}")
    print(
        "\nThat rate describes this corpus and no other traffic. It is a starting "
        "point that says where it came from, which is more than the default ever did."
    )
    if abs(achieved - target) > 1e-9:
        print(
            f"\nThe curve is a step function on {len(prompts)} prompts, so "
            f"{100 * target:.0f}% may not be reachable exactly. "
            f"`--sweep` shows every rate that is."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
