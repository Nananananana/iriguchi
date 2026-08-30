"""mamori as a scanner, against the real mamori.

Skipped entirely when it is absent, which is the configuration iriguchi is
designed to work in. The interesting failures are at the seam, and a seam only
exists when something real is on both sides -- so these do not use a fake.

The section to read is `TestWhatDoesNotTravel`. mamori's `EntityReport` carries
a `preview`, a `confidence` and a detector name, and none of the three may reach
a `Finding`. `Finding` has nowhere to put them, so the tests are about what the
adapter chose not to look up rather than about what it dropped.
"""

from __future__ import annotations

import pytest

from contracts import SensitivityScannerContract
from iriguchi.application.routing import PromptRouter
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.sensitivity import Sensitivity, SensitivityLevel
from iriguchi.errors import ScanError
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.infrastructure.scanners.mamori_scanner import (
    MamoriScanner,
    SiblingState,
    mamori_state,
)
from iriguchi.ports.scanner import SensitivityScanner

_STATE, _DETAIL = mamori_state()

#: **Skip on absent, never on broken.** The gate used to be
#: `not mamori_is_available()`, which is true in both cases -- so a mamori that
#: was installed and would not import made this entire file disappear and the
#: build go green. This is the only place the mamori boundary is checked, and it
#: went quiet exactly when the boundary had moved.
pytestmark = pytest.mark.skipif(
    _STATE is SiblingState.ABSENT, reason="mamori is not installed; the seam has one side"
)


def test_mamori_is_installed_and_importable() -> None:
    """A broken sibling is a finding, not a skip.

    Runs whenever mamori is installed at all, so the difference between "absent"
    and "cannot be imported" produces a failure with a reason rather than an
    empty test run.
    """
    assert _STATE is SiblingState.AVAILABLE, (
        f"mamori is installed and will not import: {_DETAIL}. Every test below would "
        "otherwise have been skipped, and this file is the only place the mamori "
        "boundary is checked."
    )


BOTH = frozenset(Destination)

#: Everything the fallback scanner is blind to, by its own admission.
#: `tests/test_fallback_scanner.py::TestWhatItMisses` asserts it misses these.
FALLBACK_BLIND_SPOTS = (
    "田中と打ち合わせの予定です",
    "Dear Jane Doe, thanks for your note.",
    "株式会社さくら商事の件です",
)


def findings(text: str) -> list[tuple[str, str]]:
    return [(f.rule, text[f.span.start : f.span.end]) for f in MamoriScanner().scan(text)]


class TestTheContract(SensitivityScannerContract):
    def make_scanner(self) -> SensitivityScanner:
        return MamoriScanner()


class TestItClosesTheFallbacksGaps:
    """The measured reason ADR-0005 exists.

    Each of these is a test in `test_fallback_scanner.py::TestWhatItMisses`
    asserting the opposite. The two files together are the argument for
    installing mamori, stated as behaviour rather than as a claim.
    """

    @pytest.mark.parametrize("text", FALLBACK_BLIND_SPOTS)
    def test_mamori_finds_what_the_fallback_cannot(self, text: str) -> None:
        assert FallbackScanner().scan(text) == (), "the fallback's gap moved; update both files"
        assert MamoriScanner().scan(text), f"mamori found nothing in {text!r}"

    def test_a_name_without_an_honorific(self) -> None:
        """The single largest gap in the fallback, closed."""
        assert any(rule.startswith("mamori.person") for rule, _ in findings("田中と打ち合わせです"))


class TestWhatDoesNotTravel:
    """mamori knows more than a `Finding` can carry, and that is the design.

    ADR-0032 names three of these explicitly as things a record describing
    protected text may never contain. iriguchi is the tool that sees every
    prompt, so it is the one where carrying them would cost the most.
    """

    SENSITIVE = "田中太郎さんへ tanaka@example.com から連絡がありました。"

    def test_a_finding_has_no_field_for_a_preview(self) -> None:
        """`EntityReport.preview` is a masked form of the original.

        Masked is not absent -- mamori's own words -- and a preview in an
        explanation would put a partial value in every place the explanation
        goes.
        """
        import dataclasses

        from iriguchi.domain.sensitivity import Finding

        assert {f.name for f in dataclasses.fields(Finding)} == {"rule", "source", "span"}

    def test_no_finding_renders_any_of_the_prompt(self) -> None:
        rendered = repr(MamoriScanner().scan(self.SENSITIVE))
        assert "田中太郎" not in rendered
        assert "tanaka@example.com" not in rendered

    def test_a_finding_carries_no_confidence(self) -> None:
        """A confidence describes how a value was found, which is a statement
        about the value. It is also a threshold waiting to happen, and a
        threshold is a score -- which ADR-0003 keeps out of this axis."""
        for finding in MamoriScanner().scan(self.SENSITIVE):
            assert not hasattr(finding, "confidence")

    def test_the_rule_names_a_kind_and_the_scanner(self) -> None:
        """`mamori.person` is a kind and a count, which is exactly the shape
        ADR-0032 admits for a reader who holds the text -- and exactly the shape
        it warns must not be logged at a lower classification than the prompt.
        See iriguchi's ADR-0012."""
        rules = {rule for rule, _ in findings(self.SENSITIVE)}
        assert all(rule.startswith("mamori.") for rule in rules)
        assert all("." in rule for rule in rules)


class TestItProposesAndDoesNotDecide:
    def test_a_credential_is_reported_rather_than_refused(self) -> None:
        """mamori's default policy blocks a credential. Under the permissive
        policy this adapter uses, it reports one instead -- so iriguchi's own
        policy decides what it means, and the reason a person reads is "a
        credential was found" rather than "the scanner broke"."""
        found = MamoriScanner().scan("api_key = AKIAIOSFODNN7EXAMPLE")
        assert found
        assert Sensitivity.from_findings(found).level is SensitivityLevel.RESTRICTED

    def test_it_raises_rather_than_returning_nothing_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one thing the port forbids. `()` and "I broke" are
        indistinguishable at the call site, and only one of them is safe."""
        scanner = MamoriScanner()

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("the rule table did not load")

        monkeypatch.setattr("mamori.PrivacySession", explode)
        with pytest.raises(ScanError, match="mamori could not scan"):
            scanner.scan("anything")


class TestItLeavesNothingBehind:
    def test_scanning_twice_gives_the_same_answer(self) -> None:
        """A session per scan, closed. Nothing accumulates between calls, and a
        placeholder allocated while answering a question does not survive into
        the next one."""
        scanner = MamoriScanner()
        first = scanner.scan(TestWhatDoesNotTravel.SENSITIVE)
        second = scanner.scan(TestWhatDoesNotTravel.SENSITIVE)
        assert first == second

    def test_a_fresh_scanner_agrees_with_a_used_one(self) -> None:
        used = MamoriScanner()
        used.scan("田中さんへ")
        assert used.scan("鈴木さんへ") == MamoriScanner().scan("鈴木さんへ")


class TestThroughTheRouter:
    def test_a_name_the_fallback_misses_now_stays_local(self) -> None:
        """End to end, and the reason the seam is worth its setup cost."""
        prompt = "田中と二つの案を比較して、計算量を証明してください。"

        with_fallback = PromptRouter(FallbackScanner(), RulesEstimator()).route(prompt, BOTH)
        with_mamori = PromptRouter(MamoriScanner(), RulesEstimator()).route(prompt, BOTH)

        assert with_fallback.route is Route.EXTERNAL, "the fallback's gap moved"
        assert with_mamori.route is Route.LOCAL
        assert {r.destination for r in with_mamori.removed} == {Destination.EXTERNAL}

    def test_the_explanation_says_which_scanner_found_it(self) -> None:
        """The fallback is expected to be wrong sometimes and mamori much less
        so. A person reading an explanation needs to know which they are
        looking at."""
        decision = PromptRouter(MamoriScanner(), RulesEstimator()).route("田中と打ち合わせ", BOTH)
        assert all(f.source == "mamori" for f in decision.sensitivity.findings)


class TestTheToolSaysWhichScannerAnswered:
    """`config` and `doctor` name the scanner, because changing it changes what
    leaves this machine. A person cannot check a guarantee they cannot see."""

    def run_cli(self, *argv: str) -> str:
        import io

        from iriguchi.interfaces.cli.main import main

        out = io.StringIO()
        main(list(argv), out=out)
        return out.getvalue()

    def test_config_says_mamori_when_it_is_selected(self) -> None:
        assert "scanner           mamori" in self.run_cli("--scanner", "mamori", "config")

    def test_config_says_when_mamori_is_installed_and_unused(self) -> None:
        """The nudge that matters most: a person who installed it and forgot the
        flag is getting the 67.3% miss rate while believing otherwise."""
        assert "installed but not selected" in self.run_cli("config")

    def test_doctor_names_the_trade_when_mamori_is_on(self) -> None:
        output = self.run_cli("--local", "--external", "--scanner", "mamori", "doctor")
        assert "scanner: mamori" in output
        assert "over-detects more, which is the trade" in output

    def test_doctor_nudges_when_mamori_is_installed_and_off(self) -> None:
        output = self.run_cli("--local", "--external", "doctor")
        assert "mamori is installed and not being used" in output
