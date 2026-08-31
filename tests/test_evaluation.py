"""The corpus, the scorer, and the floor that is a gate.

Most of this file guards the corpus rather than the code. A fixture that quietly
lost its adversaries, a generator whose output stopped being reproducible, a
metric that improved because somebody added easy cases -- none of those show up
as a failing assertion anywhere else, and all of them turn the corpus from
evidence into decoration.

The gate is `test_nothing_that_had_to_stay_local_left`. Everything else is
measured and reported.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.destination import Route
from iriguchi.evaluation.case import UNRECORDED, Case, Hand, Provenance, SensitivityClass, TrapKind
from iriguchi.evaluation.dataset import DATA_DIR, load_case, load_corpus
from iriguchi.evaluation.scoring import run
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner

REPO_ROOT = Path(__file__).resolve().parent.parent

#: For the tests below, which are about a single case rather than about
#: where a file came from.
A_HAND = Provenance(text=Hand("test", "test"), labels=Hand("test", "test"))

#: Deliberately far looser than the current scores. A gate set at today's number
#: makes every honest experiment a build failure, and tuning to reach a
#: threshold is what mamori's ADR-0023 records happening. These exist to catch a
#: collapse, not to certify a level.
MAX_OVER_CAUTION = 0.40
MIN_ROUTE_ACCURACY = 0.80
#: No floor on missed findings at all, deliberately. It is 63.5% and that is the
#: measured form of ADR-0005's "install mamori" -- a gate here would be a
#: standing invitation to widen the fallback until the number looked better,
#: which is exactly how it would stop being the dumb thing it is supposed to be.


@pytest.fixture(scope="module")
def corpus() -> tuple[Case, ...]:
    return load_corpus()


@pytest.fixture(scope="module")
def router() -> PromptRouter:
    return PromptRouter(scanner=FallbackScanner(), estimator=RulesEstimator())


class TestTheCorpusIsWorthHaving:
    def test_it_is_not_empty(self, corpus: tuple[Case, ...]) -> None:
        assert len(corpus) >= 100

    def test_it_has_both_classes(self, corpus: tuple[Case, ...]) -> None:
        """Negative cases are the only way over-detection gets measured."""
        classes = {case.sensitivity for case in corpus}
        assert classes == set(SensitivityClass)

    def test_every_trap_kind_is_represented(self, corpus: tuple[Case, ...]) -> None:
        present = {case.trap for case in corpus}
        missing = sorted(kind.value for kind in TrapKind if kind not in present)
        assert not missing, f"no case covers {missing}"

    def test_the_traps_are_not_a_minority_of_the_generated_half(
        self, corpus: tuple[Case, ...]
    ) -> None:
        """The borrowed cases are all `PLAIN` by construction, so this asks the
        question where it can be answered: of the cases written to be
        adversarial, most should be."""
        generated = [case for case in corpus if case.source == "generated"]
        traps = [case for case in generated if case.trap is not TrapKind.PLAIN]
        assert len(traps) * 2 > len(generated)

    def test_every_trap_says_what_its_adversary_is(self, corpus: tuple[Case, ...]) -> None:
        """A trap with no note is a case the next reader relabels."""
        for case in corpus:
            if case.trap is not TrapKind.PLAIN:
                assert case.note, f"{case.id} is a trap with no note"

    def test_ids_are_unique(self, corpus: tuple[Case, ...]) -> None:
        ids = [case.id for case in corpus]
        assert len(set(ids)) == len(ids)

    def test_every_case_says_where_it_came_from(self, corpus: tuple[Case, ...]) -> None:
        """So a bad number can be attributed to a source rather than to the
        corpus as a whole."""
        assert all(case.source for case in corpus)
        assert {case.source for case in corpus} >= {"generated", "borrowed:mamori"}


class TestTheLoaderRefusesRatherThanGuesses:
    def test_an_unknown_key_is_refused(self) -> None:
        """A misspelled `trap` that silently became `plain` would remove an
        adversary and leave the corpus reporting as though it still covered
        that case."""
        with pytest.raises(ValueError, match="unknown keys"):
            load_case(
                {
                    "id": "x",
                    "prompt": "hello",
                    "sensitivity": "may_leave",
                    "band": "low",
                    "trapp": "plain",
                },
                "test",
                A_HAND,
            )

    def test_an_unknown_format_version_is_refused(self, tmp_path: Path) -> None:
        from iriguchi.evaluation.dataset import load_cases

        path = tmp_path / "future.json"
        path.write_text(json.dumps({"format_version": 99, "samples": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="format_version"):
            load_cases(path)

    def test_a_trap_without_a_note_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="no note"):
            load_case(
                {
                    "id": "x",
                    "prompt": "hello",
                    "sensitivity": "may_leave",
                    "band": "low",
                    "trap": "hidden_secret",
                },
                "test",
                A_HAND,
            )


class TestTheGeneratorIsReproducible:
    def test_running_it_twice_changes_nothing(self) -> None:
        """No model, no seed. A regression in the fixtures is a diff rather than
        a mystery, and that only holds while this passes."""
        path = DATA_DIR / "generated.json"
        before = path.read_bytes()
        subprocess.run(  # noqa: S603
            [sys.executable, str(REPO_ROOT / "tools" / "generate_cases.py")],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
        )
        assert path.read_bytes() == before

    def test_the_oracle_refuses_a_corpus_that_is_all_one_class(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from generate_cases import check

        problems = check(
            [
                {
                    "id": "a",
                    "prompt": "hello",
                    "sensitivity": "may_leave",
                    "band": "low",
                    "trap": "plain",
                    "note": "",
                }
            ]
        )
        assert any("all one sensitivity class" in problem for problem in problems)

    def test_the_oracle_refuses_a_real_looking_address(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from generate_cases import check

        problems = check(
            [
                {
                    "id": "a",
                    "prompt": "write to someone@arealcompany.jp",
                    "sensitivity": "must_stay_local",
                    "band": "low",
                    "trap": "plain",
                    "note": "",
                }
            ]
        )
        assert any("reserved example domains" in problem for problem in problems)


class TestWhatTheRouterScores:
    def test_nothing_that_had_to_stay_local_left(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        """**The gate.** Floor of zero, and the only one in the project.

        There is no number of correct decisions that buys one of these.
        """
        report = run(router, corpus)
        assert report.leak_rate == 0.0, report.render()

    def test_over_caution_has_not_collapsed(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        report = run(router, corpus)
        assert report.over_caution_rate <= MAX_OVER_CAUTION, report.render()

    def test_route_accuracy_has_not_collapsed(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        report = run(router, corpus)
        assert report.route_accuracy >= MIN_ROUTE_ACCURACY, report.render()

    def test_deciding_is_fast_enough_to_be_invisible(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        """ADR-0008's one v0.1 floor. Generous by two orders of magnitude: the
        median is well under a millisecond and this catches an accidental
        quadratic, not a slow afternoon."""
        report = run(router, corpus)
        assert report.median_latency_ms < 50.0, report.render()

    def test_the_scanner_misses_most_of_it_and_that_is_reported(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        """The measured form of ADR-0005's "install mamori".

        Asserted as a *range*, not a floor. The upper bound catches a collapse;
        the lower bound catches somebody quietly widening the fallback until the
        number looks respectable, which is how it would stop being the dumb
        thing it is supposed to be. Closing this properly means installing
        mamori, not editing regexes here.
        """
        report = run(router, corpus)
        assert 0.4 <= report.missed_finding_rate <= 0.8, report.render()


class TestTheReportSaysWhatHappened:
    def test_it_names_every_metric(self, router: PromptRouter, corpus: tuple[Case, ...]) -> None:
        rendered = run(router, corpus).render()
        for label in (
            "missed findings",
            "leak rate",
            "over-caution",
            "route accuracy",
            "band accuracy",
            "decision latency",
        ):
            assert label in rendered

    def test_it_puts_coverage_before_the_leak_rate(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        """Reading order is the point. A 0% leak rate over easy prompts says the
        complexity axis kept them local, not that the scanner worked."""
        rendered = run(router, corpus).render()
        assert rendered.index("missed findings") < rendered.index("leak rate")

    def test_it_lists_what_was_missed(self, router: PromptRouter, corpus: tuple[Case, ...]) -> None:
        report = run(router, corpus)
        assert report.missed_findings
        assert "missed (" in report.render()

    def test_an_empty_corpus_reports_zeroes_rather_than_dividing_by_none(
        self, router: PromptRouter
    ) -> None:
        report = run(router, ())
        assert report.total == 0
        assert report.leak_rate == 0.0
        assert report.median_latency_ms == 0.0


class TestTheExpectedRouteIsDerived:
    def test_it_comes_from_the_policy_and_not_the_fixture(
        self, router: PromptRouter, corpus: tuple[Case, ...]
    ) -> None:
        """No case names a route, and none should.

        Writing it into the fixtures would copy the policy into the corpus,
        after which a policy change would need a corpus edit to stay "correct" —
        which is how a corpus stops being evidence about the code.
        """
        for outcome in run(router, corpus).outcomes:
            expected = (
                Route.LOCAL
                if outcome.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL
                else outcome.expected_route
            )
            assert outcome.expected_route in (Route.LOCAL, Route.EXTERNAL)
            if outcome.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL:
                assert outcome.expected_route is expected


class TestACaseRefusesToBeNonsense:
    """Guards on the fixture format itself. All three are things a hand-edited
    or half-generated file would produce."""

    BASE: ClassVar[dict[str, str]] = {
        "id": "x",
        "prompt": "hello",
        "sensitivity": "may_leave",
        "band": "low",
        "trap": "plain",
    }

    def test_a_case_needs_an_id(self) -> None:
        with pytest.raises(ValueError, match="must have an id"):
            load_case({**self.BASE, "id": ""}, "test", A_HAND)

    def test_a_case_needs_a_prompt(self) -> None:
        with pytest.raises(ValueError, match="no prompt"):
            load_case({**self.BASE, "prompt": "   "}, "test", A_HAND)

    def test_the_corpus_refuses_duplicate_ids_across_files(self, tmp_path: Path) -> None:
        """Two files can each be valid and still collide. Loading them together
        is the only place that can be seen, so it is checked there."""
        from iriguchi.evaluation.dataset import load_corpus as load

        for name in ("a.json", "b.json"):
            (tmp_path / name).write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "source": "t",
                        "provenance": {
                            "text": {"produced_by": "t", "authored_by": "t"},
                            "labels": {"produced_by": "t", "authored_by": "t"},
                        },
                        "samples": [self.BASE],
                    }
                ),
                encoding="utf-8",
            )
        with pytest.raises(ValueError, match="duplicate case ids"):
            load(tmp_path)


class TestTheCorpusShipsInTheWheel:
    """The data lives inside the package, not beside it.

    `load_corpus()` resolves `DATA_DIR` relative to the module, so an installed
    wheel that dropped the JSON would raise on first use rather than at build
    time. Cheap to check here.
    """

    def test_the_data_directory_is_inside_the_package(self) -> None:
        import iriguchi

        assert DATA_DIR.is_relative_to(Path(iriguchi.__file__).parent)

    def test_both_files_are_there(self) -> None:
        names = {path.name for path in DATA_DIR.glob("*.json")}
        assert names == {"generated.json", "borrowed-mamori.json"}


class TestProvenanceIsWrittenDownBeforeItIsGuessed:
    """A generator is a hand, and `generated` does not name it.

    Right now `tools/generate_cases.py` was written by whoever writes
    iriguchi's rules — one hand, known. That is the same position tsumugi was
    in with twenty cases whose `origin` said `drafted` and where nothing
    recorded *what* had drafted them. It became unrecoverable the moment a
    second producer existed, and the only available repair was to write a
    default into the field whose job is to hold a fact.

    The window here closes when a model drafts its first case: `generated`
    would then mean two things and the twenty-one already committed could only
    be told apart by guessing.
    """

    def test_both_corpora_say_whose_text_and_whose_labels(self, corpus: tuple[Case, ...]) -> None:
        for case in corpus:
            assert case.provenance.is_recorded, f"{case.id} does not say where it came from"

    def test_the_generated_half_names_this_repository_as_both_hands(
        self, corpus: tuple[Case, ...]
    ) -> None:
        """It measures whether the rules do what their author intended, and the
        record says so rather than leaving `generated` to imply otherwise."""
        generated = next(case for case in corpus if case.source == "generated")
        assert generated.provenance.text.produced_by == "tools/generate_cases.py"
        assert generated.provenance.text.authored_by == "iriguchi"
        assert generated.provenance.labels.authored_by == "iriguchi"

    def test_the_borrowed_half_names_two_different_hands(self, corpus: tuple[Case, ...]) -> None:
        """mamori wrote the prose; a rule here assigned the labels. Recorded as
        `borrowed:mamori` alone, that was one word for two hands — and it named
        the more flattering one."""
        borrowed = next(case for case in corpus if case.source == "borrowed:mamori")
        assert borrowed.provenance.text.authored_by == "mamori"
        assert borrowed.provenance.labels.authored_by == "iriguchi"
        assert borrowed.provenance.text.authored_by != borrowed.provenance.labels.authored_by

    def test_a_file_that_does_not_say_is_refused(self, tmp_path: Path) -> None:
        """Not defaulted. A default here is a guess in the field whose only job
        is to hold a fact, and it is one line away at every moment."""
        from iriguchi.evaluation.dataset import load_cases

        path = tmp_path / "silent.json"
        path.write_text(
            json.dumps({"format_version": 1, "source": "t", "samples": []}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="declares no provenance"):
            load_cases(path)

    def test_an_empty_hand_is_refused_but_unrecorded_is_not(self) -> None:
        """`unrecorded` is a value; `""` is a silence that reads as a claim.

        An empty field says "nothing to declare". The word says "not written
        down". Those are opposite statements about the same absence, and only
        one of them is ever true by accident.
        """
        with pytest.raises(ValueError, match="is empty"):
            Hand(produced_by="", authored_by="x")
        assert Hand().produced_by == UNRECORDED
        assert not Provenance(text=Hand(), labels=Hand()).is_recorded

    def test_a_case_defaults_to_unrecorded_rather_than_to_here(self) -> None:
        """Constructing a case without provenance must not silently claim this
        repository wrote it — that is the guess the whole field exists to
        prevent."""
        case = load_case(
            {
                "id": "x",
                "prompt": "hello",
                "sensitivity": "may_leave",
                "band": "low",
                "trap": "plain",
            },
            "test",
            Provenance(text=Hand(), labels=Hand()),
        )
        assert not case.provenance.is_recorded


class TestTheProvenanceReaderRefusesRatherThanGuesses:
    """Unknown keys and missing halves, refused the same way settings are.

    A misspelled `authored_by` that silently became `unrecorded` would turn a
    recorded fact into a declared absence — which is the one direction this
    field must never move on its own, because the absence is then indelible and
    looks deliberate.
    """

    def file_with(self, tmp_path: Path, provenance: object) -> Path:
        path = tmp_path / "case.json"
        path.write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "source": "t",
                    "provenance": provenance,
                    "samples": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_an_unknown_top_level_key(self, tmp_path: Path) -> None:
        from iriguchi.evaluation.dataset import load_cases

        path = self.file_with(
            tmp_path,
            {
                "text": {"produced_by": "a", "authored_by": "b"},
                "labels": {"produced_by": "a", "authored_by": "b"},
                "prose": {"produced_by": "a"},
            },
        )
        with pytest.raises(ValueError, match="unknown provenance keys"):
            load_cases(path)

    def test_a_missing_half(self, tmp_path: Path) -> None:
        """Text without labels is not half a record; it is a record that will be
        read as though the missing half agreed with the present one."""
        from iriguchi.evaluation.dataset import load_cases

        path = self.file_with(tmp_path, {"text": {"produced_by": "a", "authored_by": "b"}})
        with pytest.raises(ValueError, match="does not say who produced its labels"):
            load_cases(path)

    def test_a_misspelled_field(self, tmp_path: Path) -> None:
        from iriguchi.evaluation.dataset import load_cases

        path = self.file_with(
            tmp_path,
            {
                "text": {"produced_by": "a", "authoured_by": "b"},
                "labels": {"produced_by": "a", "authored_by": "b"},
            },
        )
        with pytest.raises(ValueError, match="unknown keys"):
            load_cases(path)
