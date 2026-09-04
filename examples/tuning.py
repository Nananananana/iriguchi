"""Retune one rule, watch the route move -- and watch the veto refuse to.

    python examples/tuning.py

Two claims this project makes, both visible in one run.

**Complexity is a preference.** It is arithmetic over hand-assigned weights, and
every one of those weights is reachable. Raising a single rule's weight moves the
band, and the band moves the route.

**Sensitivity is a veto.** It removes destinations, and nothing on the other axis
adds one back. The last case below scores 0.80 -- the top band, the same tuning
that just sent a prompt outward -- and stays local, because the prompt has an
email address in it. That is not a tie being broken in the veto's favour; the
external destination was removed before the score was consulted at all
(ADR-0003).

Nothing here calls a model, opens a socket, or writes a file.
"""

from __future__ import annotations

from iriguchi import route
from iriguchi.infrastructure.estimators.rules import RulesEstimator, RulesSettings

PROMPT = "Compare both approaches and say which is better."
WITH_PII = PROMPT + " Contact tanaka@example.com."


def show(label: str, prompt: str, estimator: RulesEstimator | None = None) -> None:
    decision = route(prompt, local=True, external=True, estimator=estimator)
    complexity = decision.complexity
    print(
        f"  {label:22} {decision.route.value:9} "
        f"score {complexity.score:.2f}  band {complexity.band.value}"
    )
    for reason in decision.reasons:
        print(f"      {reason.detail}")
    for removed in decision.removed:
        print(f"      removed {removed.destination.value}: {removed.reason.detail}")


def main() -> None:
    print(f"\nprompt: {PROMPT!r}\n")
    show("default", PROMPT)

    # One rule, by id. Not a global sensitivity dial and not a fork -- the other
    # twenty markers keep the weights they were measured with.
    louder = RulesEstimator(RulesSettings(marker_weights={"complexity.multi-step": 0.8}))
    print()
    show("multi-step at 0.80", PROMPT, louder)

    print(f"\nsame tuning, prompt now: {WITH_PII!r}\n")
    show("the veto wins", WITH_PII, louder)
    print(
        "\nThe score is identical and the route is not. Complexity asked for the "
        "\nlarger model; sensitivity had already taken it off the table.\n"
    )


if __name__ == "__main__":
    main()
