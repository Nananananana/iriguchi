"""Presidio behind the port, checked without Presidio and against it.

Two different things live in this file and they are worth separating.

`interop/presidio.py` speaks Presidio's *shape* and imports nothing -- it
converts results somebody else's analyzer produced. This is the other half:
iriguchi **running** Presidio, which needs the install, and which is the first
followable answer to the built-in scanner's 63.5% miss rate. mamori is not on
PyPI (`docs/feasibility.md` F2), so until it is, `pip install
"iriguchi[presidio]"` is the only route to detection worth having.

The tests below run with Presidio absent, which is how CI runs, by standing a
fake analyzer in its place. That covers the mapping and every refusal. What it
cannot cover is whether the real `AnalyzerEngine` returns what this adapter
thinks it does -- `TestAgainstTheRealPresidio` does that, and skips when the
package is not there, the same bargain the mamori seam makes.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from iriguchi.domain.sensitivity import Finding
from iriguchi.errors import ScanError
from iriguchi.infrastructure.scanners.presidio_scanner import (
    SOURCE,
    PresidioScanner,
    presidio_state,
)

REAL = presidio_state()[0]

#: What the stubbed `spacy.util.is_package` admits to having. A set rather than
#: a constant `True`, so the refusal path can be reached with a model name that
#: is not in it.
_INSTALLED_MODELS = {"en_core_web_lg"}


@dataclass
class _Result:
    """The three attributes this adapter reads off a `RecognizerResult`."""

    entity_type: str
    start: int
    end: int
    score: float = 0.85


class _Engine:
    """An analyzer that returns what it was told to, and records the call.

    The call is recorded because the interesting decisions in this adapter are
    about **what is passed to Presidio** -- the language, the entity list, the
    score threshold -- and an adapter that quietly drops one of those looks
    identical from the outside until the day it matters.
    """

    def __init__(self, results: list[_Result] | Exception) -> None:
        self._results = results
        self.calls: list[dict[str, Any]] = []

    def analyze(self, **kwargs: Any) -> list[_Result]:
        self.calls.append(kwargs)
        if isinstance(self._results, Exception):
            raise self._results
        return self._results


@pytest.fixture
def fake_presidio(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[_Engine]]:
    """Presidio, as far as this module can tell.

    Injected into `sys.modules` rather than monkeypatching the adapter's
    attributes, because the adapter imports `AnalyzerEngine` **inside**
    `__init__` on purpose -- a fixture that patched around that would stop
    exercising the deferred import, which is the thing keeping `iriguchi doctor`
    fast and keeping the package installable with nothing.
    """
    built: list[_Engine] = []
    holder: dict[str, list[_Result] | Exception] = {"results": []}

    def engine(*args: Any, **kwargs: Any) -> _Engine:
        made = _Engine(holder["results"])
        built.append(made)
        return made

    module = ModuleType("presidio_analyzer")
    module.AnalyzerEngine = engine  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "presidio_analyzer", module)

    # spaCy too, because the adapter checks the model is present before letting
    # Presidio build -- Presidio fetches a missing one over the network from a
    # constructor, and that guard is the reason this fixture has to stub two
    # packages rather than one.
    spacy = ModuleType("spacy")
    spacy.util = SimpleNamespace(is_package=lambda name: name in _INSTALLED_MODELS)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "spacy", spacy)
    monkeypatch.setattr(
        "iriguchi.infrastructure.scanners.presidio_scanner.presidio_state",
        lambda: (True, ""),
    )
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name, package=None: SimpleNamespace() if name == "presidio_analyzer" else None,
    )
    built.append  # noqa: B018 - keeps the list referenced for the type checker
    yield built
    holder["results"] = []


def _scanner(results: list[_Result], **kwargs: Any) -> PresidioScanner:
    scanner = PresidioScanner(**kwargs)
    scanner._engine._results = results
    return scanner


class TestWhenItIsNotInstalled:
    """Which is how CI runs, and how most readers meet it."""

    def test_the_state_says_so(self) -> None:
        if REAL:
            pytest.skip("presidio-analyzer is installed here")
        usable, detail = presidio_state()
        assert not usable
        assert detail

    def test_the_message_names_the_extra_and_the_model(self) -> None:
        """Two steps, and somebody told only the first gets an install that
        raises on construction with a spaCy error they have no context for.
        The commonest way this adapter fails is a missing language model."""
        if REAL:
            pytest.skip("presidio-analyzer is installed here")
        _, detail = presidio_state()
        assert "iriguchi[presidio]" in detail
        assert "spacy download" in detail

    def test_constructing_refuses_rather_than_scanning_nothing(self) -> None:
        """A scanner that returns no findings because it could not run is a
        veto that quietly stopped working."""
        if REAL:
            pytest.skip("presidio-analyzer is installed here")
        with pytest.raises(ScanError, match="not installed"):
            PresidioScanner()

    def test_importing_the_module_still_works(self) -> None:
        """At construction, not at import -- so `iriguchi doctor` can report it
        as absent without the CLI failing to start."""
        import iriguchi.infrastructure.scanners.presidio_scanner as module

        assert module.SOURCE == "presidio"

    def test_the_registry_refuses_it_with_the_reason(self) -> None:
        from iriguchi.errors import ConfigurationError
        from iriguchi.infrastructure.registry import SCANNERS

        if REAL:
            pytest.skip("presidio-analyzer is installed here")
        with pytest.raises(ConfigurationError, match="registered and cannot be used"):
            SCANNERS.build("presidio")

    def test_route_says_which_of_the_two_problems_it_is(self) -> None:
        """*No such scanner* and *you do not have that one* send a reader to fix
        different things."""
        from iriguchi import route
        from iriguchi.errors import ConfigurationError

        if REAL:
            pytest.skip("presidio-analyzer is installed here")
        with pytest.raises(ConfigurationError, match="not the same as it not existing"):
            route("hello", scanner="presidio", local=True)


class TestWhatItAsksPresidioFor:
    def test_the_defaults_are_passed_through(self, fake_presidio: list[_Engine]) -> None:
        scanner = _scanner([])
        scanner.scan("Contact Zoe at zoe@example.com")
        [call] = scanner._engine.calls
        assert call["language"] == "en"
        assert call["score_threshold"] == 0.5

    def test_every_entity_by_default(self, fake_presidio: list[_Engine]) -> None:
        """`None`, not a curated list. A list that looked sensible would be
        iriguchi deciding a medical licence number is not sensitive."""
        scanner = _scanner([])
        scanner.scan("anything")
        assert scanner._engine.calls[0]["entities"] is None

    def test_a_caller_can_narrow_it(self, fake_presidio: list[_Engine]) -> None:
        scanner = _scanner([], entities=["PERSON", "EMAIL_ADDRESS"])
        scanner.scan("anything")
        assert scanner._engine.calls[0]["entities"] == ["PERSON", "EMAIL_ADDRESS"]

    def test_the_threshold_goes_to_presidio_and_not_applied_here(
        self, fake_presidio: list[_Engine]
    ) -> None:
        """**The decision this file exists to protect.** Presidio's score is a
        confidence and iriguchi has none. Filtering here would mean iriguchi
        holding a threshold, and a threshold is a number somebody lowers until
        the leak rate looks acceptable. It is filtered where it means what it
        says, by the knob Presidio's authors documented."""
        scanner = _scanner([_Result("PERSON", 0, 3, score=0.01)], score_threshold=0.9)
        assert scanner._engine.calls == []
        findings = scanner.scan("Zoe")
        assert scanner._engine.calls[0]["score_threshold"] == 0.9
        # The low-scoring result still becomes a finding, because filtering it
        # was Presidio's job and Presidio said it passed.
        assert len(findings) == 1


class TestWhatComesBack:
    def test_a_result_becomes_a_finding(self, fake_presidio: list[_Engine]) -> None:
        [finding] = _scanner([_Result("PERSON", 8, 11)]).scan("Contact Zoe")
        assert finding == Finding(rule="presidio.person", source=SOURCE, span=finding.span)
        assert (finding.span.start, finding.span.end) == (8, 11)

    def test_no_score_survives_the_boundary(self, fake_presidio: list[_Engine]) -> None:
        """A `Finding` has nowhere to put a confidence, and that is the design
        rather than a gap -- `interop/presidio.py` argues it at length."""
        [finding] = _scanner([_Result("PERSON", 0, 3, score=0.42)]).scan("Zoe")
        assert not hasattr(finding, "score")
        assert "0.42" not in repr(finding)

    def test_findings_are_ordered_by_offset(self, fake_presidio: list[_Engine]) -> None:
        """So two runs over one prompt produce the same explanation. Presidio
        returns recogniser order, which is not a promise it makes."""
        out_of_order = [_Result("EMAIL_ADDRESS", 20, 35), _Result("PERSON", 8, 11)]
        findings = _scanner(out_of_order).scan("Contact Zoe at zoe@example.com")
        assert [f.span.start for f in findings] == [8, 20]

    def test_nothing_found_is_an_empty_tuple(self, fake_presidio: list[_Engine]) -> None:
        assert _scanner([]).scan("Summarise this article.") == ()

    def test_a_failure_is_raised_rather_than_swallowed(
        self, fake_presidio: list[_Engine], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-0002 turns this into the most restrictive route with a reason
        that says so. Returning `()` would turn a broken scanner into a clean
        prompt."""
        scanner = _scanner([])
        scanner._engine._results = RuntimeError("spaCy exploded")
        with pytest.raises(ScanError, match="spaCy exploded"):
            scanner.scan("anything")

    def test_it_satisfies_the_port(self, fake_presidio: list[_Engine]) -> None:
        from iriguchi.ports.scanner import SensitivityScanner

        assert isinstance(_scanner([]), SensitivityScanner)


class TestThroughTheFrontDoor:
    def test_a_finding_removes_the_external_destination(
        self, fake_presidio: list[_Engine], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of adopting it: Presidio's names reach the veto."""
        from iriguchi.application.routing import PromptRouter
        from iriguchi.domain.destination import Destination
        from iriguchi.infrastructure.registry import ESTIMATORS

        scanner = _scanner([_Result("PERSON", 8, 11)])
        router = PromptRouter(scanner=scanner, estimator=ESTIMATORS.build("rules"))
        decision = router.route(
            "Contact Zoe and prove the lemma, step by step, comparing both.",
            frozenset({Destination.LOCAL, Destination.EXTERNAL}),
        )
        assert not decision.leaves_the_machine
        assert [f.source for f in decision.sensitivity.findings] == [SOURCE]

    def test_the_explanation_names_presidio_and_carries_no_value(
        self, fake_presidio: list[_Engine]
    ) -> None:
        """ADR-0006: rule ids, spans and types, never a matched value. A scanner
        arriving from outside does not get an exemption from that."""
        from iriguchi.application.routing import PromptRouter
        from iriguchi.domain.destination import Destination
        from iriguchi.infrastructure.registry import ESTIMATORS

        scanner = _scanner([_Result("PERSON", 8, 11)])
        router = PromptRouter(scanner=scanner, estimator=ESTIMATORS.build("rules"))
        decision = router.route("Contact Zoe", frozenset({Destination.LOCAL}))
        rendered = " ".join(reason.detail for reason in decision.reasons)
        assert "Zoe" not in rendered
        assert SOURCE in rendered or any(f.source == SOURCE for f in decision.sensitivity.findings)


@pytest.mark.skipif(not REAL, reason="presidio-analyzer is not installed")
class TestAgainstTheRealPresidio:
    """The half the fake cannot answer.

    An adapter that has only ever met a stub is an adapter whose assumptions
    about the real library are untested -- and the assumptions here are exactly
    the kind that a stub written by the same person will happily agree with:
    that `analyze` takes those keywords, that results carry `entity_type`,
    `start` and `end`, that offsets are code points.

    Skipped when the package is absent, which is how CI runs. That is a real gap
    and it is the same one the mamori seam accepts, for the same reason: the
    install is 600MB and a language model.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def scanner() -> PresidioScanner:
        try:
            return PresidioScanner()
        except ScanError as failure:
            pytest.skip(f"presidio is installed and would not build: {failure}")

    def test_it_finds_a_name_the_built_in_scanner_misses(self, scanner: PresidioScanner) -> None:
        """The reason this adapter exists. `docs/measurements.md` records the
        fallback missing English names entirely, and this is that gap closing."""
        from iriguchi.infrastructure.scanners.fallback import FallbackScanner

        prompt = "Please summarise the memo that Katherine Whitfield sent."
        assert FallbackScanner().scan(prompt) == (), "the fallback now finds this; rewrite the test"
        found = scanner.scan(prompt)
        assert found, "presidio found nothing in a sentence containing a full name"
        assert any(f.rule == "presidio.person" for f in found), [f.rule for f in found]

    def test_the_offsets_land_on_the_name(self, scanner: PresidioScanner) -> None:
        """Code points, not bytes. The two disagree on every non-ASCII prompt,
        and a consumer that guesses wrong highlights the wrong words."""
        prompt = "Please summarise the memo that Katherine Whitfield sent."
        person = next(f for f in scanner.scan(prompt) if f.rule == "presidio.person")
        assert "Katherine" in prompt[person.span.start : person.span.end]

    def test_an_email_is_found(self, scanner: PresidioScanner) -> None:
        found = scanner.scan("Reply to katherine.whitfield@example.com by Friday.")
        assert any("email" in f.rule for f in found), [f.rule for f in found]

    def test_a_clean_prompt_is_clean(self, scanner: PresidioScanner) -> None:
        """A scanner that finds something in everything removes the external
        destination always, which is the same as not having one."""
        assert scanner.scan("Summarise this article in three lines.") == ()


class TestItWillNotLetPresidioReachTheNetwork:
    """The behaviour that made this adapter more than a wrapper.

    `AnalyzerEngine()` calls `_download_spacy_model_if_needed`, which calls
    `spacy.cli.download`, which shells out and fetches **382MB** from GitHub.
    Observed, not read: constructing a scanner in a clean venv printed
    `Downloading en-core-web-lg (382.1MiB)` from inside the constructor.

    For most libraries that is a convenience. Here it is disqualifying --
    iriguchi's claim is that the decision happens locally, before any request,
    and a scanner that opens a connection **while being built** has broken that
    before reading a prompt.
    """

    def test_a_missing_model_is_refused_before_the_engine_is_built(
        self, fake_presidio: list[_Engine]
    ) -> None:
        with pytest.raises(ScanError, match="not installed"):
            PresidioScanner(model="en_core_web_trf")
        assert fake_presidio == [], "an engine was constructed, which is where the download lives"

    def test_the_refusal_names_the_command_and_the_size(self, fake_presidio: list[_Engine]) -> None:
        """A refusal that does not say how to proceed is an obstacle. One that
        does not say why is one somebody works around."""
        with pytest.raises(ScanError) as raised:
            PresidioScanner(model="en_core_web_trf")
        message = str(raised.value)
        assert "python -m spacy download en_core_web_trf" in message
        assert "382MB" in message

    def test_a_present_model_builds_normally(self, fake_presidio: list[_Engine]) -> None:
        """The floor. A guard that refuses everything passes both assertions
        above and makes the scanner unusable."""
        PresidioScanner(model="en_core_web_lg")
        assert len(fake_presidio) == 1
