"""Picking an algorithm by name, and where the bands begin.

Two things arrive together because they are the same change: the choice behind
each port used to be a boolean in the composition root, and the thresholds used
to be three module constants. Both are now values somebody can name.

The research this borrows from is narrow and worth stating exactly. **RouteLLM**
(Apache-2.0, LMSYS) frames a router as a score plus a cost threshold α
calibrated to a target rate, because *"send 30% to the big model"* is a sentence
an operator can hold an opinion about and *"0.7"* is not. Their score is learned
from preference data; iriguchi's is rules, by ADR-0004. **The calibration half
transfers without the learning half**, and that is all that was taken.

What was deliberately *not* taken: RouteLLM's matrix-factorisation and
BERT-classifier routers need embeddings and a model in the deciding path, and
the privacy-preserving routing literature reaches for secure multi-party
computation. Both are the wrong shape for a tool whose dependency list is its
threat model.
"""

from __future__ import annotations

from types import ModuleType

import pytest

from iriguchi.config import IriguchiConfig
from iriguchi.domain.complexity import DEFAULT_THRESHOLDS, Complexity, ComplexityBand, Thresholds
from iriguchi.errors import ConfigurationError
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS, Choice, Registry
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.ports.estimator import ComplexityEstimator
from iriguchi.ports.scanner import SensitivityScanner


class TestTheRegistry:
    @pytest.mark.parametrize("registry", [SCANNERS, ESTIMATORS], ids=["scanners", "estimators"])
    def test_it_has_something_in_it(self, registry: Registry[object]) -> None:
        """A floor. An empty registry would make every test below pass while
        answering nothing, which is the shape `empty_parameter_set_mark` was
        turned on for."""
        assert registry.names
        assert registry.default in registry.names

    @pytest.mark.parametrize("registry", [SCANNERS, ESTIMATORS], ids=["scanners", "estimators"])
    def test_every_entry_says_what_it_costs(self, registry: Registry[object]) -> None:
        """A menu with no prices is the thing this project exists not to be.
        Ten words, because a one-word trade is a shrug."""
        for choice in registry:
            assert len(choice.trade.split()) >= 10, f"{choice.name}'s trade is not one"
            assert choice.summary.strip()

    def test_an_unknown_name_is_refused_with_the_alternatives(self) -> None:
        """Refused rather than defaulted. Somebody who named an algorithm is
        relying on it, and quietly giving them another is the worst available
        outcome -- the same rule as an unknown setting."""
        with pytest.raises(ConfigurationError, match="no scanner called"):
            SCANNERS.build("presidio")
        with pytest.raises(ConfigurationError, match=r"\['fallback', 'mamori'\]"):
            SCANNERS.build("presidio")

    def test_unknown_and_unavailable_are_different_sentences(self) -> None:
        """ "There is no such algorithm" and "you do not have that one" send a
        reader to fix different things, so they are not one message."""
        unavailable: Registry[SensitivityScanner] = Registry(
            "scanner",
            {
                "fallback": SCANNERS.describe("fallback"),
                "absent": Choice(
                    name="absent",
                    summary="s",
                    trade="a trade long enough to satisfy the ten word floor above it here",
                    build=FallbackScanner,
                    available=lambda: (False, "it is not installed"),
                ),
            },
            default="fallback",
        )
        with pytest.raises(ConfigurationError, match="not the same as it not existing"):
            unavailable.build("absent")

    def test_what_it_builds_satisfies_the_port(self) -> None:
        assert isinstance(SCANNERS.build("fallback"), SensitivityScanner)
        assert isinstance(ESTIMATORS.build("rules"), ComplexityEstimator)

    def test_the_default_scanner_is_not_the_best_available(self) -> None:
        """ADR-0005, as a check rather than a paragraph. Changing the scanner
        changes what leaves this machine, and that is not a thing to inherit
        from what happens to be installed."""
        assert SCANNERS.default == "fallback"


class TestChoosingFromTheEnvironment:
    def test_a_named_estimator_reaches_the_router(self) -> None:
        config = IriguchiConfig.from_env({"IRIGUCHI_ESTIMATOR": "rules"})
        assert config.router().estimator.__class__.__name__ == "RulesEstimator"

    def test_an_unknown_name_from_the_environment_is_refused(self) -> None:
        config = IriguchiConfig.from_env({"IRIGUCHI_ESTIMATOR": "routellm"})
        with pytest.raises(ConfigurationError, match="no estimator called"):
            config.router()

    def test_a_misspelt_setting_name_is_still_refused(self) -> None:
        """The older rule, still holding after four new keys. A typo that
        silently does nothing is worse than an error."""
        with pytest.raises(ConfigurationError, match="unknown settings"):
            IriguchiConfig.from_env({"IRIGUCHI_ESTIMATORS": "rules"})


class TestTheAlgorithmsCommand:
    """`iriguchi algorithms` is the menu. A list of names with no prices is
    what this project exists not to be, so the command prints the trade for
    every entry and marks the one this configuration would use."""

    @staticmethod
    def _run(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> str:
        import io
        import os

        from iriguchi.interfaces.cli import main as cli

        for key in [name for name in os.environ if name.startswith("IRIGUCHI_")]:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        out = io.StringIO()
        assert cli.main(["algorithms"], out) == cli.EXIT_OK
        return out.getvalue()

    def test_it_lists_every_registered_name_with_its_trade(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        printed = self._run({}, monkeypatch)
        for registry in (SCANNERS, ESTIMATORS):
            for choice in registry:
                assert choice.name in printed
                assert choice.trade[:40] in printed

    def test_it_marks_what_this_configuration_would_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default, and not the best available. Somebody reading this needs
        to know which one is about to see their prompts."""
        printed = self._run({}, monkeypatch)
        assert f"* {SCANNERS.default}" in printed

    def test_it_reports_the_bands_in_force(self, monkeypatch: pytest.MonkeyPatch) -> None:
        printed = self._run({"IRIGUCHI_HIGH_AT": "0.4"}, monkeypatch)
        assert "high at 0.4" in printed
        assert "calibrate" in printed


class TestTheThresholds:
    def test_the_default_is_what_shipped_before_the_type_existed(self) -> None:
        assert (DEFAULT_THRESHOLDS.moderate_at, DEFAULT_THRESHOLDS.high_at) == (0.3, 0.7)
        assert DEFAULT_THRESHOLDS.short_circuit_at == 2

    def test_a_name_is_or_is_not_in_the_registry(self) -> None:
        """`in`, so a caller can ask before building rather than by catching."""
        assert "fallback" in SCANNERS
        assert "presidio" not in SCANNERS

    def test_a_moderate_threshold_outside_the_range_is_refused_too(self) -> None:
        """Both ends checked, not just `high_at`. A validator that guards one
        field of a pair is the shape a mutation run finds."""
        with pytest.raises(ValueError, match=r"moderate_at is -0.1"):
            Thresholds(moderate_at=-0.1)

    def test_an_inverted_pair_is_refused(self) -> None:
        """`moderate_at` above `high_at` is not a strange configuration -- it is
        one where `MODERATE` can never be returned, and a band nothing can
        produce is the same shape as a check that cannot fail."""
        with pytest.raises(ValueError, match="unreachable"):
            Thresholds(moderate_at=0.9, high_at=0.5)

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_a_threshold_outside_the_score_range_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            Thresholds(high_at=bad)

    def test_a_short_circuit_of_zero_is_refused(self) -> None:
        """At zero every estimate short-circuits to HIGH, including an empty
        one -- so every prompt would escalate and the axis would be gone."""
        with pytest.raises(ValueError, match="every estimate"):
            Thresholds(short_circuit_at=0)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"moderate_at": 0.0, "high_at": 0.0},
            {"moderate_at": 1.0, "high_at": 1.0},
            {"moderate_at": 0.0, "high_at": 1.0},
            {"short_circuit_at": 1},
        ],
        ids=["both at zero", "both at one", "the whole range", "one escalating signal"],
    )
    def test_the_edges_of_the_permitted_range_are_permitted(self, kwargs: dict[str, float]) -> None:
        """The fencepost, in the validators this change added.

        A mutation run found `<= 1.0` and `< 1` surviving the flip to `< 1.0`
        and `<= 1`, because nothing built a `Thresholds` at either edge. That is
        the same class of gap the band comparisons had an hour earlier, in code
        written after finding it -- **knowing a shape does not make you see it
        in your own new lines.**
        """
        assert Thresholds(**kwargs)  # type: ignore[arg-type]

    def test_equal_thresholds_are_allowed_and_remove_the_middle_band(self) -> None:
        """`moderate_at == high_at` is not inverted, so it is permitted -- and
        it collapses MODERATE rather than making it unreachable by accident.
        Somebody who wants two bands should be able to say so."""
        from iriguchi.domain.complexity import Signal, SignalKind

        two_bands = Thresholds(moderate_at=0.5, high_at=0.5)
        below = Complexity.from_signals(
            (Signal(rule="t", kind=SignalKind.LEXICAL, weight=0.4, escalating=False),), two_bands
        )
        at = Complexity.from_signals(
            (Signal(rule="t", kind=SignalKind.LEXICAL, weight=0.5, escalating=False),), two_bands
        )
        assert below.band is ComplexityBand.LOW
        assert at.band is ComplexityBand.HIGH

    def test_lowering_the_high_threshold_moves_a_prompt_up_a_band(self) -> None:
        """The point of making them configurable, in one assertion."""
        from iriguchi.domain.complexity import Signal, SignalKind

        signals = (Signal(rule="t.one", kind=SignalKind.LEXICAL, weight=0.45, escalating=False),)
        assert Complexity.from_signals(signals).band is ComplexityBand.MODERATE
        lowered = Complexity.from_signals(signals, Thresholds(high_at=0.4))
        assert lowered.band is ComplexityBand.HIGH

    def test_a_setting_that_is_not_a_number_is_refused(self) -> None:
        config = IriguchiConfig.from_env({"IRIGUCHI_HIGH_AT": "hight"})
        with pytest.raises(ConfigurationError, match="not a number"):
            config.thresholds()

    def test_a_setting_that_inverts_the_pair_is_refused_by_name(self) -> None:
        config = IriguchiConfig.from_env({"IRIGUCHI_MODERATE_AT": "0.9", "IRIGUCHI_HIGH_AT": "0.5"})
        with pytest.raises(ConfigurationError, match="unreachable"):
            config.thresholds()

    def test_nothing_set_is_the_default(self) -> None:
        assert IriguchiConfig.from_env({}).thresholds() == DEFAULT_THRESHOLDS


class TestTheCalibrationTool:
    """The arithmetic, not the corpus. What the tool reports about the corpus
    is a measurement and belongs in `docs/measurements.md`."""

    @staticmethod
    def _tool() -> ModuleType:
        """Typed as a module rather than `object`.

        `object` type-checked and made every attribute access below an error --
        the same mistake `Registry.__iter__` had an hour ago. A return type wide
        enough to accept anything has stopped describing the function.
        """
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import calibrate

        return calibrate

    def test_the_candidates_include_each_score_and_a_hair_above(self) -> None:
        """A threshold only matters where it crosses a score. `>=` makes a
        score its own boundary, so the first threshold that *excludes* it is
        the interesting neighbour."""
        calibrate = self._tool()
        found = calibrate.candidates([0.5])
        assert 0.5 in found
        assert any(0.5 < value < 0.5 + 1e-6 for value in found)
        assert 0.0 in found and 1.0 in found

    def test_the_rate_is_measured_through_the_router_and_not_from_scores(self) -> None:
        """A prompt the scanner vetoes stays local whatever its band, so a rate
        computed from scores alone would promise an escalation the router will
        not deliver. The gap is exactly the corpus's sensitive half."""
        calibrate = self._tool()
        sensitive = ["Contact tanaka@example.com and prove the lemma, step by step."]
        rate = calibrate.outward_rate(
            sensitive, "rules", "fallback", Thresholds(moderate_at=0.0, high_at=0.0)
        )
        assert rate == 0.0, "a vetoed prompt left at a threshold of zero"

    def test_a_threshold_of_zero_sends_everything_the_veto_permits(self) -> None:
        calibrate = self._tool()
        clean = ["Summarise this article in three lines."]
        assert (
            calibrate.outward_rate(
                clean, "rules", "fallback", Thresholds(moderate_at=0.0, high_at=0.0)
            )
            == 1.0
        )
