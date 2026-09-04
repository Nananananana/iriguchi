"""What a policy change would do, measured before it does it.

The review asked for this twice, and the reason it matters is the direction
rather than the count. Two changes can move the same number of prompts and be
opposites: one sends work outward, the other keeps it home. **An accuracy figure
reports both as an improvement.** A prompt that started leaving the machine is
the only one worth waking up for, so it gets its own line.

Nothing here calls a model or opens a socket, which is the point -- a policy can
be measured before anybody's prompt is affected by it.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from simulate import NOTABLE, Setup, main, routes

from iriguchi.domain.complexity import Thresholds
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.infrastructure.estimators.rules import RulesSettings


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestItMeasuresTheChange:
    def test_a_louder_marker_sends_prompts_outward(self) -> None:
        code, output, _ = run("--marker-weight", "complexity.multi-step=0.8")
        assert code == 0
        assert "change route" in output
        assert "began leaving the machine" in output

    def test_the_outward_direction_is_called_out_on_its_own(self) -> None:
        """The line an operator has to see. A count of *changed* prompts is the
        same number whether they moved home or away."""
        _, output, _ = run("--marker-weight", "complexity.multi-step=0.8")
        assert "did not leave this machine now would" in output

    def test_a_change_that_moves_nothing_says_so(self) -> None:
        """`--high-at 0.5` moves nothing on this corpus, which is F1 restated
        rather than a broken simulator -- and the report has to be able to say
        *nothing happened* without looking like a failure."""
        code, output, _ = run("--high-at", "0.5")
        assert code == 0
        assert "0 of 155" in output

    def test_a_quieter_marker_keeps_prompts_home(self) -> None:
        """The other direction, so the report is not only able to describe
        movement one way."""
        louder = Setup(
            "fallback",
            "rules",
            Thresholds(),
            RulesSettings(marker_weights={"complexity.multi-step": 0.8}),
        )
        cases = load_corpus()
        base = Setup("fallback", "rules", Thresholds(), RulesSettings())
        outward = routes(louder, cases)
        home = routes(base, cases)
        assert any(outward[i] == "external" and home[i] != "external" for i in home)

    def test_show_changed_names_the_cases(self) -> None:
        _, output, _ = run("--marker-weight", "complexity.multi-step=0.8", "--show-changed")
        assert "changed cases" in output
        assert "->" in output


class TestItRefusesRatherThanReportingNothing:
    def test_no_proposal_is_refused(self) -> None:
        """A simulation of no change is a report saying nothing changed, which
        reads as *your change is safe*."""
        code, _, err = run()
        assert code == 1
        assert "nothing was proposed" in err

    def test_a_policy_iriguchi_cannot_hold_is_refused_before_routing(self) -> None:
        """A weight above one produces a score outside [0,1]. Refused where it
        was written rather than reported as a strange confusion matrix."""
        code, _, err = run("--marker-weight", "complexity.multi-step=3")
        assert code == 1
        assert "not one iriguchi can hold" in err

    def test_a_malformed_weight_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            run("--marker-weight", "complexity.multi-step")


class TestTheReportIsHonestAboutItself:
    def test_it_names_the_corpus_size(self) -> None:
        _, output, _ = run("--marker-weight", "complexity.multi-step=0.8")
        assert f"{len(load_corpus())} cases" in output

    def test_it_prints_what_changed_between_the_two_setups(self) -> None:
        """The `from`/`to` lines. A confusion matrix with no statement of what
        was compared is a table somebody will misattribute."""
        _, output, _ = run("--marker-weight", "complexity.multi-step=0.8")
        assert "from " in output and "to " in output
        assert "complexity.multi-step" in output

    def test_every_notable_crossing_is_a_real_pair_of_routes(self) -> None:
        """A typo in `NOTABLE` would silently stop reporting a crossing -- the
        line would simply never print, which looks exactly like zero."""
        from iriguchi.domain.destination import Route

        valid = {route.value for route in Route}
        for source, target, meaning in NOTABLE:
            assert source in valid and target in valid, (source, target)
            assert meaning.strip()

    def test_it_opens_no_socket(self) -> None:
        """Asserted through the import graph, the way the examples are."""
        import ast

        source = (Path(__file__).resolve().parent.parent / "tools" / "simulate.py").read_text(
            encoding="utf-8"
        )
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & {"socket", "ssl", "http", "urllib", "requests", "httpx"}
