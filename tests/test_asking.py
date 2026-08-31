"""`ask`, which is the only thing here that sends.

The use case is small and the tests are mostly about what it does **not** do:
which of two models was called, which was not, and whether anything at all ran
when the answer was a refusal. A router that decides correctly and then asks the
wrong model is exactly as wrong as one that decides badly, and only a test that
looks at the model nobody called can tell.

Two guards at the bottom are about the wiring rather than the behaviour, and
they are the ones that will still be useful in a year: a subcommand added to the
parser and not to the dispatch chain, and a config field read from the
environment and then dropped on the floor. Both had already almost happened.
"""

from __future__ import annotations

import dataclasses
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from iriguchi.application.asking import Answer, Asker
from iriguchi.application.routing import PromptRouter
from iriguchi.config import IriguchiConfig
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.reason import Reason
from iriguchi.errors import EscalationRefusedError, ModelError
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.interfaces.cli import main as cli

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})
ONLY_LOCAL = frozenset({Destination.LOCAL})

#: Two escalating signals, which short-circuits the estimator to HIGH, with
#: nothing in it a scanner objects to. Kept as one constant because a test that
#: quietly changes the prompt is testing a different route.
#:
#: The first draft of this was a long paragraph about consensus protocols, on
#: the assumption that technical and long means complex. It fires **one** signal
#: and routes local. Length is a weak lexical signal here and the structural
#: ones do the work -- `_escalated` asserts the route rather than trusting the
#: prompt, which is the only reason that draft did not silently test the local
#: path in a class named for the outward one.
WANTS_THE_BIG_ONE = (
    "Refactor this module and explain why, step by step, with alternatives considered."
)


@dataclass
class _Model:
    """Records that it was asked, and what with."""

    reply: str = "an answer"
    failure: Exception | None = None
    asked: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "a-model at http://somewhere/v1/"

    def answer(self, prompt: str) -> str:
        self.asked.append(prompt)
        if self.failure is not None:
            raise self.failure
        return self.reply


@dataclass
class _Escalation:
    protected_text: str = "<PERSON_001> asked a question"
    findings: tuple[Reason, ...] = ()
    restored: str = "Tanaka asked a question"
    closed: int = 0
    restore_failure: Exception | None = None

    def restore(self, response: str) -> str:
        if self.restore_failure is not None:
            raise self.restore_failure
        return f"{self.restored} :: {response}"

    def close(self) -> None:
        self.closed += 1


@dataclass
class _Channel:
    escalation: _Escalation = field(default_factory=_Escalation)
    prepared: list[str] = field(default_factory=list)
    failure: Exception | None = None
    name: str = "a-channel"

    def prepare(self, prompt: str) -> _Escalation:
        self.prepared.append(prompt)
        if self.failure is not None:
            raise self.failure
        return self.escalation


def _router() -> PromptRouter:
    return PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator())


def _only(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """Make `IRIGUCHI_*` be exactly `env`, and restore it afterwards."""
    for key in [name for name in os.environ if name.startswith("IRIGUCHI_")]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


class TestARefusalRunsNothing:
    def test_neither_model_is_asked(self) -> None:
        local, external = _Model(), _Model()
        answer = Asker(router=_router(), local=local, external=external, channel=_Channel()).ask(
            "hello", frozenset()
        )
        assert answer.decision.route is Route.REFUSED
        assert local.asked == []
        assert external.asked == []

    def test_the_text_is_none_and_not_empty(self) -> None:
        """An empty string prints as an answer of no words, and a refusal is
        not that. The model port refuses to collapse the same two events one
        layer down."""
        answer = Asker(router=_router()).ask("hello", frozenset())
        assert answer.text is None
        assert not answer.answered


class TestTheLocalPath:
    def test_the_local_model_answers_the_prompt_unchanged(self) -> None:
        local, external = _Model(reply="4"), _Model()
        answer = Asker(router=_router(), local=local, external=external).ask("2 + 2?", ONLY_LOCAL)
        assert answer.text == "4"
        assert local.asked == ["2 + 2?"]

    def test_the_external_model_is_not_touched(self) -> None:
        """The half of the assertion that matters. A router that decides LOCAL
        and asks the upstream anyway is the failure this project exists to
        prevent, and only the untouched model shows it."""
        external = _Model()
        Asker(router=_router(), local=_Model(), external=external, channel=_Channel()).ask(
            "2 + 2?", ONLY_LOCAL
        )
        assert external.asked == []

    def test_nothing_is_protected_on_the_way_to_a_local_model(self) -> None:
        channel = _Channel()
        Asker(router=_router(), local=_Model(), channel=channel).ask("2 + 2?", ONLY_LOCAL)
        assert channel.prepared == []

    def test_a_local_decision_with_no_local_model_is_refused(self) -> None:
        """And is not quietly served by the external one, which is the
        destination the decision ruled out."""
        external = _Model()
        with pytest.raises(EscalationRefusedError, match="not the external"):
            Asker(router=_router(), external=external, channel=_Channel()).ask("2 + 2?", ONLY_LOCAL)
        assert external.asked == []


class TestTheOutwardPath:
    @staticmethod
    def _asker(channel: _Channel, external: _Model) -> Asker:
        return Asker(router=_router(), local=_Model(), external=external, channel=channel)

    def _escalated(self, channel: _Channel, external: _Model) -> Answer:
        answer = self._asker(channel, external).ask(WANTS_THE_BIG_ONE, BOTH)
        assert answer.decision.leaves_the_machine, "the fixture prompt stopped escalating"
        return answer

    def test_the_model_sees_the_protected_text_and_not_the_prompt(self) -> None:
        """The whole point of the project, in one assertion."""
        channel, external = _Channel(), _Model()
        self._escalated(channel, external)
        assert external.asked == [channel.escalation.protected_text]
        assert WANTS_THE_BIG_ONE not in external.asked[0]

    def test_the_answer_comes_back_restored(self) -> None:
        channel, external = _Channel(), _Model(reply="the reply")
        answer = self._escalated(channel, external)
        assert answer.text == "Tanaka asked a question :: the reply"

    def test_what_the_scanner_missed_is_carried_out(self) -> None:
        """ADR-0013. iriguchi escalates only when its own scanner said CLEAR,
        so anything the protection found is something the scanner missed, and
        the person is the only one who can act on that."""
        missed = Reason(
            rule="mamori-channel.protected-email",
            source="mamori-channel",
            span=None,
            detail="mamori protected 1 EMAIL value the scanner did not find",
        )
        channel = _Channel(escalation=_Escalation(findings=(missed,)))
        answer = self._escalated(channel, _Model())
        assert answer.missed == (missed,)

    def test_the_mapping_is_released_even_when_the_model_fails(self) -> None:
        """The highest-value object in the round trip, at the moment a caller is
        least likely to remember it exists."""
        channel = _Channel()
        with pytest.raises(ModelError):
            self._asker(channel, _Model(failure=ModelError("upstream is down"))).ask(
                WANTS_THE_BIG_ONE, BOTH
            )
        assert channel.escalation.closed == 1

    def test_the_mapping_is_released_when_restoration_fails(self) -> None:
        channel = _Channel(escalation=_Escalation(restore_failure=ModelError("half of one")))
        with pytest.raises(ModelError):
            self._asker(channel, _Model()).ask(WANTS_THE_BIG_ONE, BOTH)
        assert channel.escalation.closed == 1

    def test_a_refused_escalation_sends_nothing(self) -> None:
        channel = _Channel(failure=EscalationRefusedError("mamori blocked a credential"))
        external = _Model()
        with pytest.raises(EscalationRefusedError):
            self._asker(channel, external).ask(WANTS_THE_BIG_ONE, BOTH)
        assert external.asked == []

    @pytest.mark.parametrize(
        ("channel", "external"),
        [(None, _Model()), (_Channel(), None), (None, None)],
        ids=["no channel", "no model", "neither"],
    )
    def test_an_outbound_route_without_both_halves_is_refused(
        self, channel: Any, external: Any
    ) -> None:
        """There is no path that sends unprotected, by construction: half of an
        outbound path is not a degraded outbound path."""
        with pytest.raises(EscalationRefusedError, match="unprotected"):
            Asker(router=_router(), local=_Model(), external=external, channel=channel).ask(
                WANTS_THE_BIG_ONE, BOTH
            )


class TestTheCommandLine:
    @staticmethod
    def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch, **env: str) -> tuple[int, str]:
        """Run the CLI with exactly these settings and no others.

        Every `IRIGUCHI_*` already in the environment is removed first. A test
        that inherits a developer's real configuration passes or fails for
        reasons that are not in the test, and this suite already had a rule
        about it.
        """
        _only(monkeypatch, env)
        out = io.StringIO()
        return cli.main(argv, out), out.getvalue()

    def test_dry_run_asks_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The flag `route` accepts and ignores means something here, because
        this command can send."""
        asked: list[str] = []
        monkeypatch.setattr(
            "iriguchi.infrastructure.models.openai_compatible.OpenAICompatibleModel.answer",
            lambda self, prompt: asked.append(prompt) or "",  # type: ignore[func-returns-value]
        )
        code, printed = self._run(
            ["ask", "--dry-run", "2 + 2?"],
            monkeypatch,
            IRIGUCHI_LOCAL="1",
            IRIGUCHI_LOCAL_URL="http://127.0.0.1:11434/v1",
            IRIGUCHI_LOCAL_MODEL="a-model",
        )
        assert code == cli.EXIT_OK
        assert asked == []
        assert "Nothing was asked" in printed

    def test_a_refusal_exits_two_and_asks_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        code, printed = self._run(["ask", "hello"], monkeypatch)
        assert code == cli.EXIT_REFUSED
        assert "answered" not in printed

    def test_a_missing_endpoint_names_the_setting(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Not "connection refused" for a host nobody named.

        `main` returns an exit code rather than raising, which is its whole
        contract. The first version of this test asserted `raised.value.code !=
        0 or True` -- a tautology, and one written while looking straight at the
        thing it was supposed to check.
        """
        code, _ = self._run(["ask", "hello"], monkeypatch, IRIGUCHI_LOCAL="1")
        assert code == cli.EXIT_ERROR
        assert "IRIGUCHI_LOCAL_URL" in capsys.readouterr().err

    def test_it_answers_and_says_which_model_did(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The path everything else exists to reach, and it had no test.

        Coverage said 96% of `main.py` and the six uncovered lines were the
        ones that print an answer -- the feature. A refusal test and a dry-run
        test between them exercise every branch except the one a person
        actually uses.
        """
        monkeypatch.setattr(
            "iriguchi.infrastructure.models.openai_compatible.OpenAICompatibleModel.answer",
            lambda self, prompt: "4",
        )
        code, printed = self._run(
            ["ask", "2 + 2?"],
            monkeypatch,
            IRIGUCHI_LOCAL="1",
            IRIGUCHI_LOCAL_URL="http://127.0.0.1:11434/v1",
            IRIGUCHI_LOCAL_MODEL="a-model",
        )
        assert code == cli.EXIT_OK
        assert "a-model at http://127.0.0.1:11434/v1/ answered:" in printed
        assert printed.rstrip().endswith("4")

    def test_the_route_is_printed_before_the_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A person reading a terminal should see where their words went before
        they see what came back. Reversed, the route scrolls away above a long
        answer and is never read."""
        monkeypatch.setattr(
            "iriguchi.infrastructure.models.openai_compatible.OpenAICompatibleModel.answer",
            lambda self, prompt: "an answer",
        )
        _, printed = self._run(
            ["ask", "2 + 2?"],
            monkeypatch,
            IRIGUCHI_LOCAL="1",
            IRIGUCHI_LOCAL_URL="http://127.0.0.1:11434/v1",
            IRIGUCHI_LOCAL_MODEL="a-model",
        )
        assert printed.index("local") < printed.index("answered:")

    def test_what_the_scanner_missed_is_printed_above_the_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-0013's finding is about the decision, not about the reply, and a
        person scrolling to the answer would never see it underneath."""
        out = io.StringIO()
        missed = Reason(
            rule="mamori-channel.protected-email",
            source="mamori-channel",
            span=None,
            detail="mamori protected 1 EMAIL value the scanner did not find",
        )
        answer = Answer(
            decision=_router().route("2 + 2?", ONLY_LOCAL),
            text="an answer",
            model="a-model",
            missed=(missed,),
        )
        monkeypatch.setattr(cli, "_read", lambda prompt: "2 + 2?")
        monkeypatch.setattr("iriguchi.application.asking.Asker.ask", lambda self, t, a: answer)
        _only(
            monkeypatch,
            {
                "IRIGUCHI_LOCAL": "1",
                "IRIGUCHI_LOCAL_URL": "http://127.0.0.1:11434/v1",
                "IRIGUCHI_LOCAL_MODEL": "a-model",
            },
        )
        code = cli.main(["ask", "2 + 2?"], out)
        printed = out.getvalue()
        assert code == cli.EXIT_OK
        assert "missed by the scanner" in printed
        assert printed.index("missed by the scanner") < printed.index("answered:")

    def test_dry_run_on_an_outbound_route_shows_what_would_leave(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The first thing --dry-run has ever had worth looking at, and the
        reason ADR-0014 refused the proxy: protecting and sending have to be
        separable for this to exist at all."""
        code, printed = self._run(
            ["ask", "--dry-run", WANTS_THE_BIG_ONE],
            monkeypatch,
            IRIGUCHI_LOCAL="1",
            IRIGUCHI_LOCAL_URL="http://127.0.0.1:11434/v1",
            IRIGUCHI_LOCAL_MODEL="a-model",
            IRIGUCHI_EXTERNAL="1",
            IRIGUCHI_EXTERNAL_URL="https://api.example.com/v1",
            IRIGUCHI_EXTERNAL_MODEL="a-big-model",
        )
        assert code == cli.EXIT_OK
        assert "Nothing was asked" in printed


class TestTheWiringGuards:
    """Two things that were one edit away from being silently wrong."""

    def test_every_subcommand_has_a_dispatch_branch(self) -> None:
        """The parser and the `if` chain in `main` are two lists that must
        agree, and nothing made them.

        `main` ends in a stated `AssertionError` for exactly this, which is the
        right shape -- but it only fires when somebody runs the command. This
        fires when somebody runs the tests.
        """
        parser = cli.build_parser()
        groups = parser._subparsers._group_actions  # type: ignore[union-attr]
        commands = sorted(str(name) for name in (groups[0].choices or {}))
        source = Path(str(cli.__file__)).read_text(encoding="utf-8")
        missing = [name for name in commands if f'args.command == "{name}"' not in source]
        assert not missing, (
            f"{missing} can be typed on the command line and reach no branch in "
            f"`main`. argparse accepts them, so the failure is at run time and "
            f"looks like a crash rather than a missing feature."
        )

    def test_the_config_carries_every_field_it_was_not_asked_about(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_config` rebuilt the object from three named fields, so anything
        added afterwards was read from the environment and then dropped.

        `ask`'s endpoint settings were going to be the first four. This asserts
        the copy-with-overrides rather than the constructor call.
        """
        parser = cli.build_parser()
        args = parser.parse_args(["ask", "hello"])
        env = {
            "IRIGUCHI_LOCAL": "1",
            "IRIGUCHI_LOCAL_URL": "http://127.0.0.1:11434/v1",
            "IRIGUCHI_LOCAL_MODEL": "a-model",
            "IRIGUCHI_EXTERNAL": "1",
            "IRIGUCHI_EXTERNAL_URL": "https://api.example.com/v1",
            "IRIGUCHI_EXTERNAL_MODEL": "a-big-model",
            "IRIGUCHI_EXTERNAL_KEY": "sk-secret",
        }
        from_env = IriguchiConfig.from_env(env)
        _only(monkeypatch, env)
        built = cli._config(args)

        overridden = {"use_mamori"}
        for f in dataclasses.fields(IriguchiConfig):
            if f.name in overridden:
                continue
            assert getattr(built, f.name) == getattr(from_env, f.name), (
                f"`{f.name}` was read from the environment and lost on the way "
                f"through `_config`. That function names the fields it carries, "
                f"so a new one is dropped by default rather than carried by "
                f"default."
            )

    def test_a_destination_that_can_be_routed_to_and_not_asked_is_named(self) -> None:
        """`IRIGUCHI_EXTERNAL=1` with no endpoint is a real state and a
        confusing one: `route` says a prompt may leave and `ask` refuses. Both
        are correct -- deciding needs no endpoint -- and a person who reads only
        the first would reasonably believe they were set up.

        Coverage reached this branch before this test existed, because some
        other test happened to construct that configuration. Executed is not
        asserted.
        """
        config = IriguchiConfig.from_env({"IRIGUCHI_EXTERNAL": "1"})
        described = config.describe()
        assert "no endpoint for asking" in described
        assert "IRIGUCHI_EXTERNAL_URL" in described

    def test_a_fully_configured_destination_is_not_warned_about(self) -> None:
        """The other half. A warning that always fires is a banner."""
        config = IriguchiConfig.from_env(
            {
                "IRIGUCHI_EXTERNAL": "1",
                "IRIGUCHI_EXTERNAL_URL": "https://api.example.com/v1",
                "IRIGUCHI_EXTERNAL_MODEL": "m",
            }
        )
        assert "no endpoint for asking" not in config.describe()

    def test_the_key_is_not_in_what_config_prints(self) -> None:
        """`iriguchi config` answers "what does this do with my prompts". A
        report that quotes the key turns that into a disclosure."""
        config = IriguchiConfig.from_env(
            {
                "IRIGUCHI_EXTERNAL": "1",
                "IRIGUCHI_EXTERNAL_URL": "https://api.example.com/v1",
                "IRIGUCHI_EXTERNAL_MODEL": "m",
                "IRIGUCHI_EXTERNAL_KEY": "sk-do-not-print-this",
            }
        )
        assert "sk-do-not-print-this" not in config.describe()
        assert "sk-do-not-print-this" not in repr(config)
