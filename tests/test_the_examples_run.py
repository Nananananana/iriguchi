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
