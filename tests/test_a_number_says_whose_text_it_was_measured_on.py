"""`band accuracy` is partly a fact about who wrote the corpus.

`docs/feasibility.md` F1 says the complexity estimator scores 42.9% on the 42
cases that are requests for work, against 35.7% for always answering `low`, and
that the aggregate understates how one-sided it is. What it did not say, and
what the corpus has always known, is who wrote the prompts:

    band label   text by iriguchi   text by mamori
    low                       29              134
    moderate                  17                0
    high                      17                0

**All 34 cases that ask the axis anything were written here.** An estimator
scored on prompts its own authors invented is being asked whether it agrees
with the intuitions that produced it. It does, and that is not evidence.

`provenance.text.authored_by` has been in every corpus file since the corpus
existed, is loaded onto every `Case`, and was read by nothing. So the number
went out with the reason it is weak sitting one field away, unprinted.

Two things follow, and this file holds both to measurement:

- the report says whose text a rate was measured on, and stops saying *not yet
  independent* the moment that becomes false
- `eval --corpus` scores cases somebody else holds, on their machine, and the
  report carries rates, counts and their own case ids -- no prompt text, which
  is what makes sending it back a thing they can agree to
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from iriguchi.config import IriguchiConfig
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.evaluation.scoring import SELF
from iriguchi.evaluation.scoring import run as run_evaluation
from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, main

#: Invented here and attributed to somebody else. The attribution is the only
#: thing under test: a fixture claiming another author is how the *absence* of
#: the self-scored line gets exercised without anybody's real prompts.
ELSEWHERE: list[dict[str, Any]] = [
    {
        "id": "held-001",
        "prompt": "Plan the migration of this table with zero downtime, including rollback.",
        "sensitivity": "may_leave",
        "band": "high",
        "trap": "plain",
    },
    {
        "id": "held-002",
        "prompt": "Fix the spelling in this paragraph.",
        "sensitivity": "may_leave",
        "band": "low",
        "trap": "plain",
    },
    {
        "id": "held-003",
        "prompt": "在庫の締め処理を、月末の例外も含めて設計してください。",
        "sensitivity": "may_leave",
        "band": "high",
        "trap": "plain",
    },
]


def _corpus_dir(root: Path, author: str, samples: list[dict[str, Any]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "held.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "name": "held",
                "source": "held:elsewhere",
                "provenance": {
                    "text": {"produced_by": "a person at a keyboard", "authored_by": author},
                    "labels": {"produced_by": "a person at a keyboard", "authored_by": author},
                },
                "description": "A stand-in for prompts iriguchi did not write.",
                "samples": samples,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


def _report(directory: Path | None = None) -> str:
    cases = load_corpus() if directory is None else load_corpus(directory)
    return run_evaluation(IriguchiConfig().router(), cases).render()


class TestTheBuiltInCorpusSaysWhatItIs:
    def test_every_case_that_asks_the_axis_anything_was_written_here(self) -> None:
        """The measurement behind the sentence, recomputed rather than quoted.
        If somebody adds cases from another hand, this fails and the claim in
        the docstring above has to be rewritten -- which is the point."""
        report = run_evaluation(IriguchiConfig().router(), load_corpus())
        assert report.above_low, "no case asks the axis anything, so the rest is vacuous"
        assert set(report.band_text_authors) == {SELF}

    def test_and_the_report_says_so(self) -> None:
        rendered = _report()
        assert "text by: iriguchi" in rendered
        assert "not yet an independent measurement" in rendered

    def test_the_headline_says_how_many_cases_could_not_get_it_wrong(self) -> None:
        """163 of 197 are labelled `low`, and 134 of those are borrowed PII
        strings. A band question a corpus cannot ask is one it cannot get
        wrong, and the rate reads as though it had."""
        report = run_evaluation(IriguchiConfig().router(), load_corpus())
        low = report.total - len(report.above_low)
        assert f"{low} of {report.total} are labelled `low`" in report.render()
        assert low > len(report.above_low), "the composition this line exists for has changed"


class TestAnotherHandChangesTheClaim:
    def test_the_self_scored_line_disappears(self, tmp_path: Path) -> None:
        """**The half that matters.** A warning that cannot turn off is
        decoration; this is what makes it a measurement."""
        rendered = _report(_corpus_dir(tmp_path / "c", "sora", ELSEWHERE))
        assert "text by: sora" in rendered
        assert "not yet an independent measurement" not in rendered

    def test_a_corpus_written_here_still_says_it(self, tmp_path: Path) -> None:
        """The same cases, attributed to iriguchi. Only the attribution differs,
        so this pins that the line follows provenance and not the directory."""
        rendered = _report(_corpus_dir(tmp_path / "c", SELF, ELSEWHERE))
        assert "not yet an independent measurement" in rendered

    def test_a_mixed_corpus_is_not_self_scored(self, tmp_path: Path) -> None:
        """One case from another hand is enough to stop the claim, because the
        claim is *nobody else has asked*, and somebody has."""
        mixed = [dict(ELSEWHERE[0]), {**ELSEWHERE[2], "id": "held-004"}]
        root = _corpus_dir(tmp_path / "c", SELF, mixed)
        (root / "other.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "name": "other",
                    "source": "held:other",
                    "provenance": {"text": {"authored_by": "sora"}, "labels": {}},
                    "samples": [{**ELSEWHERE[0], "id": "other-001"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report = run_evaluation(IriguchiConfig().router(), load_corpus(root))
        assert not report.band_is_self_scored
        assert set(report.band_text_authors) == {SELF, "sora"}


class TestTheReportCanBeSentBack:
    """What makes the arrangement possible at all: the holder runs it, and what
    comes back is rates, counts and the ids they chose."""

    @pytest.mark.parametrize("author", [SELF, "sora"], ids=["ours", "theirs"])
    def test_no_prompt_appears_in_the_report(self, author: str, tmp_path: Path) -> None:
        root = _corpus_dir(tmp_path / "c", author, ELSEWHERE)
        rendered = _report(root)
        for sample in ELSEWHERE:
            assert sample["prompt"] not in rendered
        for fragment in ("migration of this table", "spelling", "締め処理"):
            assert fragment not in rendered

    def test_nor_in_the_built_in_one(self) -> None:
        cases = load_corpus()
        rendered = _report()
        assert not [case.id for case in cases if case.prompt and case.prompt in rendered]

    def test_the_case_ids_do_appear(self, tmp_path: Path) -> None:
        """Not an oversight. A holder needs to know *which* case went wrong to
        look at it themselves, and the id is theirs -- they chose it, and it is
        the one part of a case iriguchi never derived from the prompt."""
        root = _corpus_dir(
            tmp_path / "c",
            "sora",
            [{**ELSEWHERE[0], "sensitivity": "must_stay_local"}],
        )
        assert "held-001" in _report(root)


class TestTheSeamRefusesRatherThanCrashes:
    """A new seam somebody else's file crosses. Twice this week one of those
    reached a person as a traceback -- a bare `OSError` from `--findings`, and a
    `ValueError` from a span the domain refuses."""

    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        return main(list(argv), out=out), out.getvalue()

    def test_a_directory_that_is_not_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _ = self._run("eval", "--corpus", "no/such/place")
        assert code == EXIT_ERROR
        assert capsys.readouterr().err.splitlines()[0].startswith("ConfigurationError: ")

    def test_a_malformed_corpus_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "broken.json").write_text('{"samples": [{"id": "x"}]}', encoding="utf-8")
        code, _ = self._run("eval", "--corpus", str(tmp_path))
        assert code == EXIT_ERROR
        assert capsys.readouterr().err.splitlines()[0].startswith("ConfigurationError: ")

    def test_a_file_that_is_not_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "notjson.json").write_text("this is not json", encoding="utf-8")
        code, _ = self._run("eval", "--corpus", str(tmp_path))
        assert code == EXIT_ERROR
        assert capsys.readouterr().err.splitlines()[0].startswith("ConfigurationError: ")

    def test_the_refusal_carries_no_part_of_the_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ADR-0021 at a seam it was written one day before. A JSON parser
        quotes what it choked on, and what it choked on is somebody's corpus."""
        (tmp_path / "notjson.json").write_text(
            "tanaka@example.com should not be in an error", encoding="utf-8"
        )
        self._run("eval", "--corpus", str(tmp_path))
        assert "tanaka@example.com" not in capsys.readouterr().err

    def test_an_empty_directory_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An empty corpus scores 100% on everything -- the shape of a check
        that cannot fail rather than a passing one."""
        code, _ = self._run("eval", "--corpus", str(tmp_path))
        assert code == EXIT_ERROR
        assert "cannot fail" in capsys.readouterr().err

    def test_a_real_corpus_is_scored(self, tmp_path: Path) -> None:
        code, printed = self._run(
            "eval", "--corpus", str(_corpus_dir(tmp_path / "c", "sora", ELSEWHERE))
        )
        assert code == EXIT_OK
        assert f"cases                {len(ELSEWHERE)}" in printed

    def test_no_corpus_flag_still_scores_the_built_in_one(self) -> None:
        code, printed = self._run("eval")
        assert code == EXIT_OK
        assert "cases                197" in printed
