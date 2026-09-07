"""The error catalogue, held to the program rather than to itself.

A catalogue of failures is the easiest document in this repository to let rot.
Nothing breaks when it goes stale: the program still fails the same way, the
sentences still read well, and the only person who finds out is a consumer whose
screen shows a kind it has never heard of -- at the moment something is already
going wrong, which is the worst moment to learn that the documentation was old.

So none of the three claims the schema makes is checked by reading:

    errors is complete       every IriguchiError subclass is accounted for
    exit_code is measured    driven through the CLI, not asserted
    reported_as resolves     through `rules --json`, the real document

The first draft of the catalogue pointed at `routing.judge-failed`. There is no
such rule -- a broken judge is reported as `cascade.judge-failed`, on the
cascade's prefix, because the cascade is where it changes anything. That was
caught by writing the check before believing the table.
"""

from __future__ import annotations

import contextlib
import io
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import iriguchi.errors as error_module
from iriguchi import __version__
from iriguchi.errors import NOT_YET_RAISED, IriguchiError, RoutingError
from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main
from iriguchi.interfaces.contract import schema
from iriguchi.interfaces.error_catalogue import (
    CONTRACT,
    ERRORS,
    NOT_A_FAILURE,
    OPEN_NAMESPACES,
)
from iriguchi.interfaces.error_catalogue import as_document as errors_document
from iriguchi.interfaces.rules import as_document as rules_document

CATALOGUED = {kind for kind, *_ in ERRORS}
QUIET = {kind for kind, *_ in NOT_A_FAILURE}


def _subclasses() -> set[str]:
    """Every `IriguchiError` subclass the package defines.

    Read off the module rather than listed, so a new exception class is in this
    set the moment somebody writes it -- which is the only way the completeness
    check below can be about the program instead of about a second list.
    """
    return {
        name
        for name, value in vars(error_module).items()
        if isinstance(value, type)
        and issubclass(value, IriguchiError)
        and value is not IriguchiError
    }


class TestItIsComplete:
    def test_there_are_exceptions_to_account_for(self) -> None:
        """The check below is a set difference, and a set difference against an
        empty set passes while checking nothing. This is the guard that stops
        a renamed module from retiring the whole file silently."""
        assert len(_subclasses()) >= 8

    def test_every_exception_is_accounted_for(self) -> None:
        """In one of three places: printed as a failure, turned into a decision,
        or declared as raised by nothing. A fourth state -- present in the code
        and in no document -- is what this forbids."""
        unaccounted = _subclasses() - CATALOGUED - QUIET - set(NOT_YET_RAISED) - {"RoutingError"}
        assert not unaccounted, f"exceptions in neither catalogue nor NOT_YET_RAISED: {unaccounted}"

    def test_nothing_is_catalogued_that_does_not_exist(self) -> None:
        """The mirror. A kind removed from the code and left in the table reads
        exactly like one that is still raised, and a consumer would keep a
        translation for a failure that can no longer happen."""
        invented = (CATALOGUED | QUIET) - _subclasses()
        assert not invented, f"catalogued and not an exception: {invented}"

    def test_the_two_lists_do_not_overlap(self) -> None:
        """A kind in both would leave a consumer unable to say whether it
        arrives as a failure or as a decision, which is the one question this
        document exists to answer."""
        assert not (CATALOGUED & QUIET)

    def test_the_quiet_ones_are_exactly_the_routing_family(self) -> None:
        """Not a coincidence worth leaving unstated. ADR-0002 turns a broken
        proposer into a restriction, and `RoutingError` is the name of that
        property -- so the two lists are drawn by the type tree, not by taste."""
        routing = {
            name
            for name in _subclasses()
            if issubclass(getattr(error_module, name), RoutingError) and name != "RoutingError"
        }
        assert routing == QUIET

    def test_nothing_still_declared_unraised_is_catalogued_as_printable(self) -> None:
        """`ContractError` is exported, documented, and raised by nothing.
        Cataloguing it would invite a consumer to write a branch for a failure
        that cannot arrive -- the same shape as a check that cannot fail."""
        assert not (set(NOT_YET_RAISED) & CATALOGUED)


class TestTheCrossReferenceResolves:
    """`reported_as` names a rule in a different document. A pointer nobody
    follows is a pointer nobody notices breaking."""

    def test_every_reported_as_is_a_real_rule(self) -> None:
        known = {entry["rule"] for entry in rules_document(__version__)["rules"]}
        named = {rule for _, rule, *_ in NOT_A_FAILURE}
        assert named <= known, f"named here and absent from `rules`: {sorted(named - known)}"

    def test_it_would_catch_the_mistake_that_was_made(self) -> None:
        """The first draft said `routing.judge-failed`. This asserts that name
        is genuinely absent, so the test above was not passing by luck."""
        known = {entry["rule"] for entry in rules_document(__version__)["rules"]}
        assert "routing.judge-failed" not in known
        assert "cascade.judge-failed" in known


class TestTheExitCodesAreMeasured:
    """Declared codes, driven. `exit_code` is the field Sora named as the reason
    they can check their own manifest against iriguchi's declaration rather than
    against a document somebody wrote once -- so it had better be true."""

    def test_a_configuration_error_exits_as_declared(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared = {kind: code for kind, code, *_ in ERRORS}["ConfigurationError"]
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        # Through a path the *code* refuses, not one argparse's `choices`
        # intercepts. The first version of this used `--scanner nosuch` and was
        # measuring argparse -- which exits rather than returning, so it never
        # reached the handler this is about.
        assert main(["route", "--findings", "no/such/file.json", "hello"]) == declared
        assert capsys.readouterr().err.splitlines()[0].startswith("ConfigurationError: ")

    @pytest.mark.parametrize(
        "kind,declared", [(k, c) for k, c, *_ in ERRORS], ids=[k for k, *_ in ERRORS]
    )
    def test_every_declared_code_is_the_code_the_handler_returns(
        self,
        kind: str,
        declared: int,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """**All four, not the one that was easy to reach.**

        The first version of this file drove `ConfigurationError` through a real
        path and left the other three declared and unchecked -- while the
        schema's own comment said each code *is the code the CLI actually
        returns*. A document that overclaims about its own checking is the exact
        failure this repository keeps finding in other people's, so it is worth
        naming here: three quarters of that sentence was not true.

        `ModelError` and `RestorationError` need a model and a real mamori, and
        `EscalationRefusedError` needs an outbound path -- none reachable in
        this environment. So the exception is raised at a seam inside the `try`,
        which measures the handler: the code returned and the name printed. That
        is what `exit_code` is a claim about. Whether each kind is *reachable*
        is a different claim, made by `NOT_YET_RAISED` and its own test.
        """
        import iriguchi.interfaces.cli.main as cli

        raised = getattr(error_module, kind)

        def _explode(_: object) -> object:
            raise raised("the seam refused, on purpose")

        monkeypatch.setattr(cli, "_config", _explode)
        assert cli.main(["route", "hello"]) == declared
        assert capsys.readouterr().err.splitlines()[0] == (f"{kind}: the seam refused, on purpose")

    def test_the_seam_really_is_inside_the_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The test above would pass just as well if `_config` were called
        outside the `try` and the exception escaped -- pytest would see the
        raise, not the return. This pins that it does not escape."""
        import iriguchi.interfaces.cli.main as cli

        def _explode(_: object) -> object:
            raise error_module.ModelError("not a SystemExit and not an escape")

        monkeypatch.setattr(cli, "_config", _explode)
        assert isinstance(cli.main(["route", "hello"]), int)

    def test_no_catalogued_kind_claims_the_refusal_code(self) -> None:
        """The collision this catalogue was written next to. `2` is a decision
        iriguchi stands behind, and a failure carrying it would tell a consumer
        that a crash was a policy answer."""
        assert all(code != EXIT_REFUSED for _, code, *_ in ERRORS)

    def test_a_refusal_still_exits_two_and_says_why(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The other half. Fixing the usage code must not have moved this one."""
        monkeypatch.delenv("IRIGUCHI_LOCAL", raising=False)
        monkeypatch.delenv("IRIGUCHI_EXTERNAL", raising=False)
        out = io.StringIO()
        assert main(["route", "hello"], out=out) == EXIT_REFUSED
        assert "REFUSED" in out.getvalue()

    def test_a_mistyped_flag_is_broken_and_not_refused(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """**The defect this found.** argparse exits 2 for a usage error and
        iriguchi publishes 2 as *refused*, so a typo reached a consumer as a
        routing refusal -- with no decision document anywhere, because none had
        been made."""
        with pytest.raises(SystemExit) as exit_code:
            main(["--nosuchflag", "route", "hello"])
        assert exit_code.value.code == EXIT_ERROR
        first = capsys.readouterr().err.splitlines()[0]
        assert first.startswith("ConfigurationError: "), first

    def test_the_usage_text_still_arrives(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Putting the kind first must not have cost the person at the terminal
        the thing they actually need, which is what the flags are."""
        with pytest.raises(SystemExit):
            main(["--nosuchflag", "route", "hello"])
        assert "usage: iriguchi" in capsys.readouterr().err


class TestTheFoldKey:
    """What a consumer keys on: the name before the colon on the first line.

    It was `iriguchi` for every failure, so four unrelated ones folded into a
    single row. These drive real failures and read the real line.
    """

    CASES: tuple[tuple[str, list[str]], ...] = (
        ("an unknown scanner", ["--scanner", "nosuch", "route", "hi"]),
        ("an unknown judge", ["--judge", "nosuch", "route", "hi"]),
        ("an unreadable findings file", ["route", "--findings", "no/such/file.json", "hi"]),
        ("a findings file that is not JSON", ["route", "--findings", "pyproject.toml", "hi"]),
    )

    @pytest.mark.parametrize("label,argv", CASES, ids=[label for label, _ in CASES])
    def test_the_first_line_begins_with_a_catalogued_kind(
        self,
        label: str,
        argv: list[str],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        try:
            code = main(argv)
        except SystemExit as stopped:
            code = int(stopped.code or 0)
        assert code != EXIT_OK, f"{label} did not fail, so there is no line to check"
        first = capsys.readouterr().err.splitlines()[0]
        kind = first.split(":", 1)[0]
        assert kind in CATALOGUED, f"{label} folds as {kind!r}, which is not in the catalogue"

    def test_it_is_no_longer_the_program_name(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The regression that matters. `iriguchi: ...` is a valid-looking name
        and would be accepted by a consumer, silently, forever."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        assert main(["route", "--findings", "no/such/file.json", "hi"]) == EXIT_ERROR
        assert not capsys.readouterr().err.startswith("iriguchi:")

    def test_the_four_cases_really_are_different_failures(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """They all fold as `ConfigurationError`, which is correct and is also
        exactly what the old bug looked like. So this asserts the *sentences*
        differ -- the part a person reads, which is where the four failures are
        actually told apart."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        sentences = set()
        for _, argv in self.CASES:
            with contextlib.suppress(SystemExit):
                main(argv)
            sentences.add(capsys.readouterr().err.splitlines()[0].split(":", 1)[1])
        assert len(sentences) == len(self.CASES)


class TestTheDocument:
    def test_it_matches_the_shipped_schema(self) -> None:
        Draft202012Validator(schema(CONTRACT)).validate(errors_document(__version__))

    def test_the_command_writes_the_same_thing(self) -> None:
        out = io.StringIO()
        assert main(["errors"], out=out) == EXIT_OK
        assert json.loads(out.getvalue()) == json.loads(
            json.dumps(errors_document(__version__), ensure_ascii=False)
        )

    def test_the_open_half_is_empty_and_that_is_a_claim(self) -> None:
        """Every kind is one of iriguchi's own class names, because an adapter
        that catches a foreign exception wraps it. An `OSError` from an
        unreadable `--findings` file escaped once and is wrapped now."""
        assert OPEN_NAMESPACES == ()
        assert errors_document(__version__)["open_namespaces"] == []

    def test_every_kind_carries_both_sentences(self) -> None:
        document: dict[str, Any] = dict(errors_document(__version__))
        for entry in list(document["errors"]) + list(document["not_a_failure"]):
            assert entry["detail"].strip() and entry["detail_ja"].strip()
            assert entry["detail"] != entry["detail_ja"]

    def test_no_entry_carries_a_message_template_or_a_path(self) -> None:
        """Asked for explicitly, and the reason is that a reader fills a
        template in from their own logs -- at which point a document that holds
        no values holds values."""
        rendered = json.dumps(errors_document(__version__), ensure_ascii=False)
        for shape in ("{}", "{0}", "%s", "/home/", "C:\\", "/tmp/"):
            assert shape not in rendered, f"the catalogue carries {shape!r}"


class TestRetryableMeansPermissionAndNotPossibility:
    """Sora asked whether asking again could *succeed*; this document answers
    whether it *may be issued*. They adopted the narrower reading, and mamori
    reached the same sentence independently:

        may the same request be issued again, unchanged -- and a failure where
        re-issuing is itself a new event is `false` even when it could succeed

    Applying it moved an entry that had been `true` since this table was
    written, so the reason is pinned here rather than left in a comment.
    """

    @staticmethod
    def _asker(external_failure: Exception) -> tuple[Any, Any, Any]:
        from dataclasses import dataclass, field

        from iriguchi.application.asking import Asker
        from iriguchi.application.routing import PromptRouter
        from iriguchi.domain.reason import Reason
        from iriguchi.infrastructure.estimators.rules import RulesEstimator
        from iriguchi.infrastructure.scanners.fallback import FallbackScanner

        @dataclass
        class _Model:
            failure: Exception | None = None
            asked: list[str] = field(default_factory=list)

            @property
            def name(self) -> str:
                return "a-model"

            def answer(self, prompt: str) -> str:
                self.asked.append(prompt)
                if self.failure is not None:
                    raise self.failure
                return "an answer"

        @dataclass
        class _Escalation:
            protected_text: str = "<PERSON_001> asked a question"
            findings: tuple[Reason, ...] = ()
            closed: int = 0

            def restore(self, response: str) -> str:
                return response

            def close(self) -> None:
                self.closed += 1

        @dataclass
        class _Channel:
            escalation: _Escalation = field(default_factory=_Escalation)
            prepared: list[str] = field(default_factory=list)
            name: str = "a-channel"

            def prepare(self, prompt: str) -> _Escalation:
                self.prepared.append(prompt)
                return self.escalation

        channel, external = _Channel(), _Model(failure=external_failure)
        asker = Asker(
            router=PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator()),
            local=_Model(),
            external=external,
            channel=channel,
        )
        return asker, channel, external

    #: Long, structural, and nothing a scanner objects to -- so the veto leaves
    #: the external destination in place and the estimator asks for it. Asserted
    #: below rather than trusted, because a prompt that quietly routed local
    #: would make every assertion here vacuous.
    WANTS_THE_BIG_ONE = (
        "Refactor this module and explain why, step by step, with alternatives considered."
    )

    def test_a_model_error_can_arise_after_the_prompt_has_left(self) -> None:
        """**The measurement that moved the entry.** `Asker._outward` raises this
        from `external.answer()`, which is the one line in the package that
        sends -- so by the time the failure exists, the prompt is gone."""
        from iriguchi.domain.destination import Destination
        from iriguchi.errors import ModelError

        asker, channel, external = self._asker(ModelError("the upstream returned 503"))
        with pytest.raises(ModelError):
            asker.ask(self.WANTS_THE_BIG_ONE, frozenset({Destination.LOCAL, Destination.EXTERNAL}))

        assert channel.prepared, "the route was not outward, so this measured nothing"
        assert external.asked, "the send never happened, so this measured nothing"
        assert channel.escalation.closed == 1

    def test_so_model_error_is_not_retryable(self) -> None:
        """Retrying re-issues the same request, and on that path re-issuing
        sends the prompt a second time. One kind spans the local path and the
        outbound one; the answer for a kind that spans them is the restrictive
        one."""
        assert {kind: retry for kind, _, _, retry, *_ in ERRORS}["ModelError"] is False

    def test_nothing_in_this_build_is_retryable(self) -> None:
        """A statement, not an oversight -- and the place a future `true` has to
        argue with. Splitting `ModelError` so the outbound failure has a name of
        its own is what would earn one back."""
        assert not [kind for kind, _, _, retry, *_ in ERRORS if retry]
