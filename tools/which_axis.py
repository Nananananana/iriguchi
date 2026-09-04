"""Which of the two axes actually decided each route.

    python tools/which_axis.py
    python tools/which_axis.py --source borrowed:mamori

iriguchi's design has two axes: sensitivity is a **veto** and complexity is a
**preference** (ADR-0003). The veto has a section in `measurements.md`, a leak
rate, a miss rate and an argument about each. The preference has never been
shown deciding anything, and this is the instrument that says how often it does.

It answers one question -- *of the prompts that were not vetoed, how many did
complexity send outward* -- and it answers it over the committed corpus with no
model, no network and no arguments required. Everything it prints is a count.

## Why this is not a section of `measure_router.py`

That tool asks a model to band a prompt and needs `--model`, a URL and a running
server. This one needs nothing, because the question is about iriguchi's own
rules rather than about anybody's judgement of them, and a measurement that
cannot be reproduced without a GPU is a measurement most readers take on trust.

## What it found the first time it was run

    complexity -> external        2    1.3%

and, split by where the case came from, **zero** of the 134 borrowed cases. The
reason is the median length of a borrowed prompt: 34 characters. They are
mamori's PII samples -- a name, a particle, an email address -- and a complexity
estimator reading one has nothing to estimate, because it is not a request for
work. So the corpus measures the veto well, which is what it was built for, and
cannot speak to the other axis at all.

That is a finding about the corpus rather than about the estimator, and the
distinction matters: the fix is prompts, not thresholds. `tools/calibrate.py
--sweep` will happily produce any outward rate you like by lowering `high_at`,
and none of those rates is evidence the axis is *right*.

Recorded in `docs/feasibility.md` as F1.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.destination import Destination
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})

#: The three ways a route is reached, in the order they are decided. Named
#: rather than derived from the decision's fields at the call site, because the
#: whole point of the report is that these three are not interchangeable.
VETO = "the veto removed external"
KEPT = "complexity kept it local"
SENT = "complexity sent it out"
ORDER = (VETO, KEPT, SENT)
#: Column headings for the by-source table. Spelled out rather than taken from
#: the first word of each phrase, which produced `the / complexity / complexity`
#: -- two columns with the same heading and the interesting one unnamed.
SHORT = {VETO: "veto", KEPT: "local", SENT: "external"}


def decided_by(prompt: str, router: PromptRouter) -> str:
    """Which axis produced the outcome for `prompt`.

    The veto is checked first because it is checked first: a prompt with a
    finding never reaches the complexity comparison, and attributing it to the
    band it happened to score would credit the preference axis with an outcome
    it had no part in.
    """
    decision = router.route(prompt, BOTH)
    if decision.sensitivity.findings:
        return VETO
    return SENT if decision.leaves_the_machine else KEPT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="only cases from this source")
    parser.add_argument("--scanner", default=SCANNERS.default, choices=SCANNERS.names)
    parser.add_argument("--estimator", default=ESTIMATORS.default, choices=ESTIMATORS.names)
    args = parser.parse_args(argv)

    router = PromptRouter(
        scanner=SCANNERS.build(args.scanner), estimator=ESTIMATORS.build(args.estimator)
    )
    cases = [c for c in load_corpus() if args.source is None or c.source == args.source]
    if not cases:
        print(f"no cases from {args.source!r}", file=sys.stderr)
        return 1

    overall: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = {}
    lengths: dict[str, list[int]] = {}
    for case in cases:
        what = decided_by(case.prompt, router)
        overall[what] += 1
        by_source.setdefault(case.source, Counter())[what] += 1
        lengths.setdefault(case.source, []).append(len(case.prompt))

    total = len(cases)
    print(f"{total} cases, scanner {args.scanner}, estimator {args.estimator}\n")
    for what in ORDER:
        print(f"  {what:28} {overall[what]:4}  {100 * overall[what] / total:5.1f}%")

    if len(by_source) > 1:
        print("\nby source" + " " * 21 + "".join(f"{SHORT[w]:>13}" for w in ORDER))
        for source, counter in sorted(by_source.items()):
            n = sum(counter.values())
            cells = "".join(f"{counter[w]:>13}" for w in ORDER)
            print(f"  {source:18} n={n:4}{cells}")

    # Printed beside the counts rather than in a footnote, because a source that
    # never reaches the second axis and a source of 34-character strings are the
    # same fact, and separating them makes the first look like an estimator bug.
    print("\nprompt length, which is why")
    for source, values in sorted(lengths.items()):
        print(
            f"  {source:18} median {statistics.median(values):5.0f}   max {max(values):5}   chars"
        )

    if overall[SENT] == 0:
        print(
            "\nNothing reached the external destination on complexity alone. "
            "That is a statement about these prompts, not about the estimator -- "
            "see docs/feasibility.md F1 before changing a threshold."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
