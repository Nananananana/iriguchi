"""The router, end to end, with the real scanner and the real estimator.

Two halves. The first is the happy path over a handful of prompts, which is
mostly a check that the pieces are wired the way the earlier files claim.

The second is failure, and it is why this file exists. A proposer that breaks
must not become a leak, and there are three ways it can break -- raising the
exception the port defines, raising something else entirely, and the one nothing
here can catch.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.complexity import Signal
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.sensitivity import Finding, SensitivityLevel
from iriguchi.errors import EstimationError, ScanError
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner

BOTH = frozenset(Destination)
LOCAL_ONLY = frozenset({Destination.LOCAL})
EXTERNAL_ONLY = frozenset({Destination.EXTERNAL})
NOTHING: frozenset[Destination] = frozenset()

SECRET = "sk-live-51H8xQeMwvJ4tRbN7cZpLdKf"


@pytest.fixture
def router() -> PromptRouter:
    return PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator())


class TestTheHappyPath:
    def test_an_easy_harmless_prompt_stays_local(self, router: PromptRouter) -> None:
        decision = router.route("この記事を要約してください", BOTH)
        assert decision.route is Route.LOCAL
        assert decision.sensitivity.level is SensitivityLevel.CLEAR

    def test_a_hard_harmless_prompt_escalates(self, router: PromptRouter) -> None:
        decision = router.route("この二つのアルゴリズムを比較して、計算量を証明してください", BOTH)
        assert decision.route is Route.EXTERNAL
        assert decision.complexity.short_circuited is True

    def test_a_hard_prompt_with_a_secret_in_it_does_not_leave(self, router: PromptRouter) -> None:
        """The sentence the whole project is for.

        Hard enough to want the big model, and it stays anyway, because
        sensitivity removed that destination before complexity was asked.
        """
        decision = router.route(
            f"この二つのアルゴリズムを比較して、計算量を証明してください。鍵は {SECRET} です",
            BOTH,
        )
        assert decision.route is Route.LOCAL
        assert not decision.leaves_the_machine
        assert {r.destination for r in decision.removed} == {Destination.EXTERNAL}

    def test_the_same_prompt_with_no_local_model_is_refused(self, router: PromptRouter) -> None:
        decision = router.route(f"鍵は {SECRET} です", EXTERNAL_ONLY)
        assert decision.route is Route.REFUSED

    def test_every_decision_explains_itself(self, router: PromptRouter) -> None:
        for available in (BOTH, LOCAL_ONLY, EXTERNAL_ONLY, NOTHING):
            decision = router.route(f"鍵は {SECRET} です", available)
            assert decision.reasons
            assert all(reason.rule and reason.detail for reason in decision.reasons)

    def test_no_reason_ever_quotes_the_prompt(self, router: PromptRouter) -> None:
        decision = router.route(f"tanaka@example.com に {SECRET} を送って", BOTH)
        rendered = repr(decision)
        assert SECRET not in rendered
        assert "tanaka@example.com" not in rendered


class RaisingScanner:
    name = "raising"

    def scan(self, text: str) -> Sequence[Finding]:
        raise ScanError("the rule table did not load")


class ExplodingScanner:
    """Raises something the port never mentions. Adapters do this."""

    name = "exploding"

    def scan(self, text: str) -> Sequence[Finding]:
        raise KeyError("locale")


class SilentlyBrokenScanner:
    """Conforming in type, catastrophic in effect. Finds nothing, ever."""

    name = "silent"

    def scan(self, text: str) -> Sequence[Finding]:
        return ()


class RaisingEstimator:
    name = "raising"

    def estimate(self, text: str) -> Sequence[Signal]:
        raise EstimationError("the marker table did not load")


class ExplodingEstimator:
    name = "exploding"

    def estimate(self, text: str) -> Sequence[Signal]:
        raise ZeroDivisionError("mean of no words")


class TestWhenTheScannerBreaks:
    """ADR-0002 at the point where it costs something."""

    @pytest.mark.parametrize("scanner", [RaisingScanner(), ExplodingScanner()])
    def test_a_decision_still_comes_out(self, scanner: object) -> None:
        router = PromptRouter(scanner=scanner, estimator=RulesEstimator())  # type: ignore[arg-type]
        assert router.route("anything at all", BOTH) is not None

    @pytest.mark.parametrize("scanner", [RaisingScanner(), ExplodingScanner()])
    def test_and_it_is_local(self, scanner: object) -> None:
        """A broken scanner costs the external route, not the afternoon."""
        router = PromptRouter(scanner=scanner, estimator=RulesEstimator())  # type: ignore[arg-type]
        decision = router.route("compare these and prove the bound", BOTH)
        assert decision.route is Route.LOCAL
        assert not decision.leaves_the_machine

    def test_a_hard_prompt_cannot_escalate_past_a_broken_scanner(self) -> None:
        """The dangerous shape: the estimator is working and says HIGH.

        If the failure were handled by ignoring it, this is the prompt that
        would go out.
        """
        router = PromptRouter(scanner=RaisingScanner(), estimator=RulesEstimator())
        decision = router.route("この補題を証明して、なぜ成り立つか説明して", BOTH)
        assert decision.complexity.prefers_the_larger_model
        assert decision.route is Route.LOCAL

    def test_the_failure_is_in_the_reasons_and_names_the_scanner(self) -> None:
        router = PromptRouter(scanner=RaisingScanner(), estimator=RulesEstimator())
        decision = router.route("anything", BOTH)
        failure = next(r for r in decision.reasons if r.rule == "routing.scanner-failed")
        assert "raising" in failure.detail
        assert "rule table did not load" in failure.detail

    def test_the_failure_sorts_among_the_statements_about_the_request(self) -> None:
        """It carries no span, so it is a statement about the request rather
        than about a place in it, and it sorts with the others of that kind.

        Not *first*. `Reason.sort_key` orders spanless reasons by source and
        then rule, which puts `policy.prefer-local` ahead of
        `routing.scanner-failed` alphabetically. That is fine and deliberately
        not fixed here: ordering by importance is a presentation decision, and
        the domain has no notion of importance to sort by. `--explain` groups
        by source and can lead with a failure if it wants to.
        """
        router = PromptRouter(scanner=RaisingScanner(), estimator=RulesEstimator())
        decision = router.route("anything", BOTH)

        spanless = [reason for reason in decision.reasons if reason.span is None]
        assert any(reason.rule == "routing.scanner-failed" for reason in spanless)

        first_spanned = next(
            (i for i, reason in enumerate(decision.reasons) if reason.span is not None),
            len(decision.reasons),
        )
        assert all(reason.span is None for reason in decision.reasons[:first_spanned])

    def test_with_no_local_model_a_broken_scanner_refuses(self) -> None:
        """Not "the external one is all that is left". ADR-0002."""
        router = PromptRouter(scanner=RaisingScanner(), estimator=RulesEstimator())
        assert router.route("anything", EXTERNAL_ONLY).route is Route.REFUSED


class TestWhenTheEstimatorBreaks:
    @pytest.mark.parametrize("estimator", [RaisingEstimator(), ExplodingEstimator()])
    def test_it_costs_answer_quality_and_nothing_else(self, estimator: object) -> None:
        router = PromptRouter(scanner=FallbackScanner(), estimator=estimator)  # type: ignore[arg-type]
        decision = router.route("この補題を証明して、なぜ成り立つか説明して", BOTH)
        assert decision.route is Route.LOCAL
        assert decision.sensitivity.level is SensitivityLevel.CLEAR

    def test_the_failure_is_reported_rather_than_swallowed(self) -> None:
        """A decision that quietly lost an axis looks exactly like one where
        that axis had no opinion. ADR-0006."""
        router = PromptRouter(scanner=FallbackScanner(), estimator=RaisingEstimator())
        decision = router.route("anything", BOTH)
        failure = next(r for r in decision.reasons if r.rule == "routing.estimator-failed")
        assert "raising" in failure.detail


class TestTheOneItCannotCatch:
    """A scanner that lies quietly, and the reason the port forbids it.

    This is not a defect in the use case. It is the consequence the port
    contract's rule exists to prevent, written down so that anybody tempted to
    relax that rule can see what it buys.
    """

    def test_a_scanner_that_returns_nothing_sends_the_prompt_out(self) -> None:
        router = PromptRouter(scanner=SilentlyBrokenScanner(), estimator=RulesEstimator())
        decision = router.route(f"この二つを比較して証明してください。鍵は {SECRET} です", BOTH)
        assert decision.route is Route.EXTERNAL
        assert decision.leaves_the_machine

    def test_the_real_scanner_finds_that_prompt(self) -> None:
        """The contrast. Nothing above is a statement about `FallbackScanner`."""
        router = PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator())
        decision = router.route(f"この二つを比較して証明してください。鍵は {SECRET} です", BOTH)
        assert decision.route is Route.LOCAL


class TestItIsStillAFunction:
    def test_the_same_prompt_decides_the_same_way(self, router: PromptRouter) -> None:
        prompt = "tanaka@example.com に連絡して、二つの案を比較してください"
        assert router.route(prompt, BOTH) == router.route(prompt, BOTH)

    def test_it_does_not_probe_for_anything(self, router: PromptRouter) -> None:
        """`available` is passed in, not discovered (ADR-0011).

        The autouse fixture in conftest.py has the network poisoned for this
        test as for every other, so a use case that went looking for a local
        model would fail here.
        """
        assert router.route("hello", NOTHING).route is Route.REFUSED
        assert router.route("hello", BOTH).route is Route.LOCAL
