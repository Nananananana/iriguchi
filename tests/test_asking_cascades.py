"""The cascade, through the use case and the command rather than the domain.

`test_the_cascade.py` covers the gate and the judges in isolation. This is the
wiring: does `Asker` actually consult a judge, does it re-ask through the
**protected** path when it escalates, does it keep the answer it replaced, and
does the command tell somebody that any of it happened.

The invariant this file exists to hold is the one that would be easiest to lose
in wiring: **there is no second, lighter way out.** An escalated answer goes
through exactly the same channel a direct external route would, so a cascade
cannot become a path that sends something the router would not have sent.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

import pytest

from iriguchi.application.asking import Asker
from iriguchi.application.routing import PromptRouter
from iriguchi.domain.answer import AnswerSignal, Weakness
from iriguchi.domain.destination import Destination
from iriguchi.domain.reason import Reason
from iriguchi.errors import JudgementError
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.interfaces.cli.main import EXIT_OK, main

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})
ONLY_LOCAL = frozenset({Destination.LOCAL})

#: Easy, clean, and short: routes LOCAL with the external destination never
#: removed, which is the only shape a cascade can act on.
EASY = "Summarise this article in three lines."
#: Carries an address, so the veto removes external before any judge runs.
SENSITIVE = "Summarise this and send it to sample.contact@example.com."


@dataclass
class _Model:
    reply: str = "a local answer."
    name: str = "a-model"
    asked: list[str] = field(default_factory=list)

    def answer(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.reply


@dataclass
class _Escalation:
    protected_text: str = "<PERSON_001> asked"
    findings: tuple[Reason, ...] = ()
    closed: int = 0

    def restore(self, response: str) -> str:
        return f"restored :: {response}"

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


@dataclass
class _Judge:
    """Says what it was told to, and records that it was consulted."""

    weak: bool = True
    failure: Exception | None = None
    name: str = "a-judge"
    seen: list[tuple[str, str]] = field(default_factory=list)

    def judge(self, prompt: str, answer: str) -> tuple[AnswerSignal, ...]:
        self.seen.append((prompt, answer))
        if self.failure is not None:
            raise self.failure
        if not self.weak:
            return ()
        return (AnswerSignal("judge.made-up", Weakness.SHAPE, 0.9),)


def _asker(judge: _Judge | None, **kwargs: object) -> Asker:
    return Asker(
        router=PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator()),
        local=kwargs.get("local", _Model()),  # type: ignore[arg-type]
        external=kwargs.get("external", _Model(reply="a bigger answer.", name="big-model")),  # type: ignore[arg-type]
        channel=kwargs.get("channel", _Channel()),  # type: ignore[arg-type]
        judge=judge,
    )


class TestWithoutAJudgeNothingChanges:
    def test_a_local_answer_is_final(self) -> None:
        """The default. A router that started making a second model call for
        everybody would be a different product."""
        answer = _asker(None).ask(EASY, BOTH)
        assert answer.text == "a local answer."
        assert answer.quality is None and answer.escalation is None
        assert not answer.cascaded

    def test_the_external_model_is_not_touched(self) -> None:
        external = _Model(reply="a bigger answer.", name="big-model")
        _asker(None, external=external).ask(EASY, BOTH)
        assert external.asked == []


class TestAWeakAnswerIsReAsked:
    def test_the_external_answer_replaces_it(self) -> None:
        answer = _asker(_Judge(weak=True)).ask(EASY, BOTH)
        assert answer.cascaded
        assert answer.text == "restored :: a bigger answer."
        assert answer.model == "big-model"

    def test_the_local_answer_is_kept(self) -> None:
        """A person told "the local answer was poor, here is a better one" is
        entitled to see the poor one -- otherwise they cannot judge the judge."""
        answer = _asker(_Judge(weak=True)).ask(EASY, BOTH)
        assert answer.superseded == "a local answer."

    def test_it_goes_through_the_protected_channel(self) -> None:
        """**The invariant most easily lost in wiring.** There is no second,
        lighter way out: an escalated prompt is protected by exactly the channel
        a direct external route would have used."""
        channel = _Channel()
        _asker(_Judge(weak=True), channel=channel).ask(EASY, BOTH)
        assert channel.prepared == [EASY]
        assert channel.escalation.closed == 1

    def test_the_external_model_never_sees_the_raw_prompt(self) -> None:
        external = _Model(reply="a bigger answer.", name="big-model")
        _asker(_Judge(weak=True), external=external).ask(EASY, BOTH)
        assert external.asked == ["<PERSON_001> asked"]

    def test_the_verdict_says_why(self) -> None:
        answer = _asker(_Judge(weak=True)).ask(EASY, BOTH)
        assert answer.escalation is not None
        assert answer.escalation.escalate
        assert "judge.made-up" in answer.escalation.reason.detail

    def test_the_judge_was_shown_the_local_answer(self) -> None:
        judge = _Judge(weak=True)
        _asker(judge).ask(EASY, BOTH)
        assert judge.seen == [(EASY, "a local answer.")]


class TestAnAdequateAnswerStays:
    def test_nothing_is_re_asked(self) -> None:
        external = _Model(reply="a bigger answer.", name="big-model")
        answer = _asker(_Judge(weak=False), external=external).ask(EASY, BOTH)
        assert answer.text == "a local answer."
        assert not answer.cascaded
        assert external.asked == []

    def test_the_verdict_is_still_recorded(self) -> None:
        """A judge that ran and said *fine* is not the same as no judge, and the
        account has to be able to tell them apart."""
        answer = _asker(_Judge(weak=False)).ask(EASY, BOTH)
        assert answer.escalation is not None
        assert not answer.escalation.escalate
        assert answer.quality is not None


class TestTheVetoWinsOverTheJudge:
    def test_a_removed_destination_stays_removed(self) -> None:
        """The whole point, at the level where it could be lost. The judge says
        weak, the answer is poor, and the prompt stays local because a finding
        took the external destination away before any of this ran."""
        external = _Model(reply="a bigger answer.", name="big-model")
        answer = _asker(_Judge(weak=True), external=external).ask(SENSITIVE, BOTH)
        assert not answer.cascaded
        assert answer.text == "a local answer."
        assert external.asked == []

    def test_and_it_says_so(self) -> None:
        answer = _asker(_Judge(weak=True)).ask(SENSITIVE, BOTH)
        assert answer.escalation is not None
        assert "not evidence about sensitivity" in answer.escalation.reason.detail

    def test_a_machine_with_no_external_destination_does_not_escalate(self) -> None:
        answer = _asker(_Judge(weak=True)).ask(EASY, ONLY_LOCAL)
        assert not answer.cascaded
        assert answer.escalation is not None
        assert "missing endpoint" in answer.escalation.reason.detail


class TestAJudgeThatBreaks:
    def test_the_local_answer_stands(self) -> None:
        """A broken judge costs quality, never safety. It cannot send anything
        anywhere -- and it must not lose the answer that already exists."""
        answer = _asker(_Judge(failure=JudgementError("the model went away"))).ask(EASY, BOTH)
        assert answer.text == "a local answer."
        assert not answer.cascaded

    def test_and_the_failure_is_reported(self) -> None:
        """A cascade that quietly stopped cascading looks exactly like one whose
        answers were all adequate."""
        answer = _asker(_Judge(failure=JudgementError("the model went away"))).ask(EASY, BOTH)
        assert answer.escalation is not None
        assert answer.escalation.reason.rule == "cascade.judge-failed"
        assert "went away" in answer.escalation.reason.detail

    def test_no_quality_is_invented(self) -> None:
        """`None`, not an adequate-looking `AnswerQuality`. No opinion was
        formed, and pretending one was is how a broken judge becomes invisible."""
        answer = _asker(_Judge(failure=JudgementError("gone"))).ask(EASY, BOTH)
        assert answer.quality is None


class TestThroughTheCommand:
    @staticmethod
    def _run(*argv: str) -> tuple[int, str]:
        out = io.StringIO()
        return main(list(argv), out=out), out.getvalue()

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in [k for k in os.environ if k.startswith("IRIGUCHI_")]:
            monkeypatch.delenv(key, raising=False)

    def test_the_flag_exists_and_names_both_judges(self) -> None:
        from iriguchi.interfaces.cli.main import build_parser

        judge = next(a for a in build_parser()._actions if a.option_strings == ["--judge"])
        assert set(judge.choices or ()) == {"rules", "consistency"}

    def test_consistency_without_a_local_model_is_refused(self) -> None:
        """A cascade over a model that does not exist is a setting that
        silently does nothing, and this project refuses those loudly.

        Asserted at the composition root rather than through `ask`, because
        `ask` would need a reachable endpoint to get that far and the network
        fence refuses one -- correctly.
        """
        from iriguchi.config import IriguchiConfig
        from iriguchi.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="no local model configured to re-ask"):
            IriguchiConfig(local=True, judge="consistency").answer_judge()

    def test_dry_run_builds_no_judge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`--dry-run` promises to construct nothing that can send, and a
        consistency judge sends -- to the local model, twice. The flag returns
        before the `Asker` exists, so naming a judge cannot make an inspection
        command start calling models.

        This is the same structural promise that made `--dry-run` work on a
        machine without mamori: a flag meaning "decide and send nothing" cannot
        require the sending half to be available.
        """
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        code, output = self._run("--judge", "consistency", "ask", "--dry-run", EASY)
        assert code == EXIT_OK
        assert "Nothing was asked" in output

    def test_an_unknown_judge_is_refused_by_the_parser(self) -> None:
        with pytest.raises(SystemExit):
            self._run("--judge", "nonesuch", "route", "hello")

    def test_no_judge_prints_no_cascade_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An absent judge is not an opinion. A line saying "not judged" on
        every ordinary run is a line people stop reading."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        _, output = self._run("route", EASY)
        assert "cascade" not in output.lower()


class TestTheJudgeIsNotPaidForNothing:
    """The defect this found by being run rather than by being read.

    A machine with a local model and no external endpoint took the second
    inference every time, then reported *there is nowhere to escalate to*.
    Correct, and after the money.

    Every refusal `escalation_possible` can give is a property of the decision
    and the machine, never of the answer -- so all of them are settled before a
    judge runs. The judge that works re-asks the local model, so this is the
    difference between one inference and two on every prompt of a machine that
    could never have escalated in the first place.
    """

    def test_no_external_destination_means_no_judgement(self) -> None:
        judge = _Judge(weak=True)
        answer = _asker(judge).ask(EASY, ONLY_LOCAL)
        assert judge.seen == [], "the judge ran with nowhere to escalate to"
        assert answer.escalation is not None
        assert "missing endpoint" in answer.escalation.reason.detail

    def test_a_vetoed_prompt_means_no_judgement(self) -> None:
        """The external destination was removed by a finding. Nothing the judge
        could say would change that, so it is not asked."""
        judge = _Judge(weak=True)
        answer = _asker(judge).ask(SENSITIVE, BOTH)
        assert judge.seen == []
        assert answer.escalation is not None
        assert "not evidence about sensitivity" in answer.escalation.reason.detail

    def test_the_local_answer_still_comes_back(self) -> None:
        """Skipping the judge must not skip the answer."""
        assert _asker(_Judge(weak=True)).ask(EASY, ONLY_LOCAL).text == "a local answer."

    def test_and_a_possible_escalation_still_consults_it(self) -> None:
        """The floor. All three assertions above pass against an `Asker` that
        never judges anything, which would be the cascade switched off."""
        judge = _Judge(weak=True)
        _asker(judge).ask(EASY, BOTH)
        assert judge.seen == [(EASY, "a local answer.")]
