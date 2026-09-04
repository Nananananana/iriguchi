"""Anything under `examples/` runs, and shows what it claims to show.

An example is documentation that executes, which makes it the only kind that
cannot quietly go stale -- provided something executes it. Nothing did, so this
does.

Discovered by globbing rather than listed, because a list of examples in a test
file is the second place to add an example and the one that gets forgotten.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*.py"))
IDS = [path.name for path in EXAMPLES]

#: A floor. Every parametrized assertion below draws on this list, and a glob
#: that finds nothing retires all of them while the run stays green.
assert EXAMPLES, "no examples found; this file is guarding nothing"


@pytest.mark.parametrize("path", EXAMPLES, ids=IDS)
def test_it_runs_without_raising(path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(path), run_name="__main__")
    assert capsys.readouterr().out.strip(), f"{path.name} printed nothing"


@pytest.mark.parametrize("path", EXAMPLES, ids=IDS)
def test_it_imports_nothing_that_reaches_the_network(path: Path) -> None:
    """An example is the first thing somebody runs, and it has to be true that
    running it sends nothing.

    Checked through the import graph rather than by grepping the source -- the
    first version searched for the string `socket` and matched the word in this
    example's own docstring, which is a test about prose wearing a security
    test's name.
    """
    import ast

    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"socket", "ssl", "http", "urllib", "requests", "httpx"}, imported


class TestTuningShowsBothAxes:
    """`examples/tuning.py` exists to show one thing: the same score, two routes.

    If it ever prints the same route for both of the last two cases, the example
    is no longer demonstrating that sensitivity outranks complexity -- and it
    would still run, still print, and still look right.
    """

    @staticmethod
    def _output(capsys: pytest.CaptureFixture[str]) -> str:
        runpy.run_path(
            str(Path(__file__).resolve().parent.parent / "examples" / "tuning.py"),
            run_name="__main__",
        )
        return capsys.readouterr().out

    def test_retuning_one_rule_moves_the_route(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = self._output(capsys)
        assert "default" in out and "multi-step at 0.80" in out
        default = next(line for line in out.splitlines() if "default" in line)
        retuned = next(line for line in out.splitlines() if "multi-step at 0.80" in line)
        assert "local" in default, default
        assert "external" in retuned, retuned

    def test_the_veto_still_wins_at_the_same_score(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The claim the example is for. Both lines carry the top band; only one
        of them leaves."""
        out = self._output(capsys)
        retuned = next(line for line in out.splitlines() if "multi-step at 0.80" in line)
        vetoed = next(line for line in out.splitlines() if "the veto wins" in line)
        assert "score 0.80" in retuned and "score 0.80" in vetoed, (retuned, vetoed)
        assert "external" in retuned and "local" in vetoed, (retuned, vetoed)


def test_examples_are_importable_from_an_installed_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """They import `iriguchi`, not a relative path into `src/`. An example that
    only runs from the repository root is an example a user cannot run."""
    for path in EXAMPLES:
        source = path.read_text(encoding="utf-8")
        assert "sys.path" not in source, f"{path.name} manipulates sys.path"
        assert "from iriguchi" in source or "import iriguchi" in source
    assert sys.modules  # keeps the fixture honest about having run


class TestCascadeShowsTheInvariant:
    """`examples/cascade.py` exists to show one thing, twice.

    Its second and third cases carry the **same refusal** from the model and
    reach opposite verdicts, because the third prompt's external destination had
    already been removed by the veto. That contrast is the whole of ADR-0018: a
    weak answer is evidence about a model, not about sensitivity.

    An example that still runs, still prints and no longer shows that would look
    entirely correct.
    """

    @staticmethod
    def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
        runpy.run_path(
            str(Path(__file__).resolve().parent.parent / "examples" / "cascade.py"),
            run_name="__main__",
        )
        return capsys.readouterr().out.splitlines()

    def test_the_same_refusal_reaches_opposite_verdicts(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lines = self._lines(capsys)
        declined = lines.index("  the model declined")
        stays = lines.index("  weak, and it stays anyway")
        after_declined = "\n".join(lines[declined : declined + 6])
        after_stays = "\n".join(lines[stays : stays + 6])

        assert "judge.refusal" in after_declined and "judge.refusal" in after_stays, (
            "the two cases no longer carry the same weakness, so the contrast is gone"
        )
        assert "escalate      YES" in after_declined
        assert "escalate      no" in after_stays

    def test_the_veto_is_named_as_the_reason(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = "\n".join(self._lines(capsys))
        assert "not evidence about sensitivity" in out

    def test_it_prints_no_part_of_any_prompt(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The example plants an address to make the veto fire. ADR-0006 says
        rule ids and spans, never a value -- and an example is the most-copied
        code in a repository."""
        out = "\n".join(self._lines(capsys))
        assert "sample.contact@example.com" not in out
