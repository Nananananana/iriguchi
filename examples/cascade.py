"""Answer locally, judge what came back, escalate only if it was poor.

    python examples/cascade.py

The complexity estimator scores **42.9%** on prompts written to test it: it
detects difficulty when a request announces it, and misses eleven of thirteen
hard prompts that do not (`docs/feasibility.md` F1). That is the ceiling on
*predicting* how hard a prompt will be before anybody has tried.

A cascade replaces the prediction with an observation. The four cases below use
answers written here rather than a running model, so this runs offline and the
logic is what is on show -- the judge reads text, and it does not care where the
text came from.

Watch the third case. The answer is the worst of the four and it stays local,
because the prompt carried an address and the veto removed the external
destination before any of this ran. **A weak answer is evidence about a model,
not about sensitivity** (ADR-0018).
"""

from __future__ import annotations

from iriguchi import route
from iriguchi.domain.answer import AnswerQuality
from iriguchi.domain.cascade import may_escalate
from iriguchi.domain.destination import Destination
from iriguchi.infrastructure.judges import RulesJudge

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})

#: Prompt, and what a small local model said back. Invented, both halves.
EXCHANGES = (
    (
        "a good answer",
        "Summarise this release note in two sentences.",
        "The release adds retry backoff and fixes a crash on empty input. "
        "Upgrading is recommended for anyone running the queue worker.",
    ),
    (
        "the model declined",
        "Plan the migration of this table with zero downtime and a rollback path.",
        "I do not know how to answer that.",
    ),
    (
        "weak, and it stays anyway",
        "Explain why this fails, and email the result to sample.contact@example.com.",
        "I cannot help with that.",
    ),
    (
        "the model came apart",
        "Compare these two designs and recommend one.",
        "Both are good.\nBoth are good.\nBoth are good.\nBoth are good",
    ),
)


def main() -> None:
    judge = RulesJudge()
    for label, prompt, answer in EXCHANGES:
        decision = route(prompt, local=True, external=True)
        quality = AnswerQuality.from_signals(judge.judge(prompt, answer))
        verdict = may_escalate(decision, quality, BOTH)

        print(f"\n  {label}")
        print(f"      first hop     {decision.route.value}")
        print(f"      answer        {quality.adequacy.value}  (score {quality.score:.2f})")
        if quality.signals:
            print(f"      because       {', '.join(s.rule for s in quality.signals)}")
        print(f"      escalate      {'YES' if verdict.escalate else 'no'}")
        print(f"      {verdict.reason.detail}")

    print(
        "\n  The third answer is the same refusal as the second and does not "
        "escalate.\n  The prompt carried an address, the veto removed the "
        "external destination,\n  and a disappointing answer is not new "
        "evidence about that.\n"
    )


if __name__ == "__main__":
    main()
