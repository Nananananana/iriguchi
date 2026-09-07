"""The README's examples, run.

A README is the one document everybody reads and the one nothing checks. Both
examples in the first screen of this one were **wrong when they were written**:
the console block was what the author expected iriguchi to print rather than
what it prints -- different offsets, a `because` line that does not exist, a
route rendered lowercase -- and the settings table listed `--moderate-at` and
`--high-at`, which are environment variables and have never been flags.

Neither would have been caught by a person reading it, because both looked
exactly like the real thing. That is the failure mode: prose about behaviour
ages silently, and a fabricated example is indistinguishable from a stale one.

So the examples run here. Not paraphrased, not approximated -- the actual lines
from the actual fenced blocks, against the actual CLI.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import pytest

from iriguchi.interfaces.cli.main import EXIT_OK, build_parser, main

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture(scope="module")
def readme() -> str:
    text = README.read_text(encoding="utf-8")
    assert text.strip(), "the README is empty, so every assertion below is about nothing"
    return text


def _console_block(readme: str, command: str) -> list[str]:
    """The output lines of the fenced block containing `command`.

    Located by the command rather than by position, so reordering the document
    does not silently point this at a different example.
    """
    marker = f"$ {command}"
    assert marker in readme, f"the README no longer contains `{marker}`"
    after = readme.split(marker, 1)[1]
    block = after.split("```", 1)[0]
    return [line.rstrip() for line in block.splitlines()[1:] if line.strip()]


def _simulate_flags() -> set[str]:
    """Every flag `tools/simulate.py` defines, asked of its own parser.

    The first version of this intercepted `argparse.parse_args` to catch the
    parser on its way past, which worked and was unreadable and would not
    typecheck. The tool exposes `build_parser()` now, the way the CLI does --
    the fix for *this is hard to inspect* was to make it inspectable.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import simulate

    return {
        action.option_strings[0]
        for action in simulate.build_parser()._actions
        if action.option_strings
    }


class TestTheConsoleExample:
    ROUTE = 'iriguchi route "Email the Q3 figures to tanaka@example.com"'

    @staticmethod
    def _actual(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        assert main(["route", "Email the Q3 figures to tanaka@example.com"], out=out) == EXIT_OK
        return [line.rstrip() for line in out.getvalue().splitlines() if line.strip()]

    def test_the_example_produces_output_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A floor. Every line of an empty claim is trivially present in
        anything, and the assertion below would pass over a deleted block."""
        assert len(self._actual(monkeypatch)) >= 5

    def test_there_is_something_being_claimed(self, readme: str) -> None:
        assert len(_console_block(readme, self.ROUTE)) >= 5, "the README's block shrank to nothing"

    def test_every_claimed_line_is_really_printed(
        self, readme: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check that would have caught the invented version. The first
        draft claimed `fallback.email-shape at 26-45`; the real offsets are
        24-42, and nothing in the world would have noticed."""
        actual = self._actual(monkeypatch)
        claimed = _console_block(readme, self.ROUTE)
        missing = [line for line in claimed if line not in actual]
        assert not missing, f"the README claims lines iriguchi does not print: {missing}"

    def test_the_offsets_in_the_example_are_the_real_ones(
        self, readme: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Called out on its own because a span is the detail a reader trusts
        most and can check least -- and it is the part the first draft got
        wrong."""
        spans = re.findall(r"at (\d+)-(\d+)", "\n".join(_console_block(readme, self.ROUTE)))
        assert spans, "the example no longer shows a span; this test is guarding nothing"
        printed = "\n".join(self._actual(monkeypatch))
        for start, end in spans:
            assert f"at {start}-{end}" in printed


class TestTheEvalExample:
    """The report block, which nothing checked until it was wrong in every row.

    The corpus grew from 155 cases to 197 and the README kept publishing the old
    six numbers -- `cases 155`, `missed findings 63.5%`, `band accuracy 96.1%`.
    Every one of them was a measurement, printed as a measurement, and stale.

    The routing example above has been checked since the day it was found
    invented. This block was in the same document, one screen down, and the
    check simply had not been pointed at it -- which is the same shape as the
    error-catalogue scan that read one module while claiming the package.
    """

    EVAL = "iriguchi --local --external eval"

    @staticmethod
    def _actual(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        assert main(["eval"], out=out) == EXIT_OK
        return [line.rstrip() for line in out.getvalue().splitlines() if line.strip()]

    def test_the_example_produces_output_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert len(self._actual(monkeypatch)) >= 6

    def test_there_is_something_being_claimed(self, readme: str) -> None:
        assert len(_console_block(readme, self.EVAL)) >= 6, "the README's block shrank to nothing"

    def test_every_claimed_line_is_really_printed(
        self, readme: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**Latency excluded, and only latency.** It is the one row that
        differs between machines, so pinning it would make the suite red on a
        busy laptop and teach everybody to ignore this file. Every rate, every
        count and both provenance lines are exact."""
        actual = self._actual(monkeypatch)
        claimed = [
            line
            for line in _console_block(readme, self.EVAL)
            if not line.strip().startswith("decision latency")
        ]
        assert claimed, "every line was excluded, so this is checking nothing"
        missing = [line for line in claimed if line not in actual]
        assert not missing, f"the README claims lines iriguchi does not print: {missing}"

    def test_the_block_still_shows_what_the_rate_rests_on(self, readme: str) -> None:
        """**The other direction, and the one that matters here.**

        Every other check in this class asserts the README claims nothing
        iriguchi does not print -- which a *shorter* README satisfies perfectly.
        Deleting the two provenance lines would leave `band accuracy 84.8%`
        standing alone and every test above green, and standing alone is exactly
        the state this change exists to end.
        """
        block = " ".join(_console_block(readme, self.EVAL))
        assert "above `low`" in block, "the README shows the rate without its population"
        assert "text by:" in block, "the README shows the rate without its author"
        assert "not yet an independent measurement" in block, (
            "the README shows `band accuracy` without the sentence that says it is "
            "an estimator agreeing with the people who wrote it. If a corpus from "
            "another hand has arrived, this test is obsolete and F1 is answered -- "
            "rewrite both rather than deleting this."
        )

    def test_the_rates_in_the_prose_are_the_rates_in_the_block(self, readme: str) -> None:
        """The sentence under the block quotes the scanner's miss rate. It said
        63.5% while the block said 61.7% -- two numbers for one fact, in one
        document, one screen apart."""
        [block_rate] = [
            line.split()[2]
            for line in _console_block(readme, self.EVAL)
            if line.strip().startswith("missed findings")
        ]
        after = readme.split(self.EVAL, 1)[1]
        prose = after[: after.index("regression floor")]
        # Line wrapping puts a newline anywhere, so the prose is flattened
        # before the rate is looked for.
        flattened = " ".join(prose.split())
        assert f"misses {block_rate}" in flattened, (
            f"the block says {block_rate} and the prose under it does not"
        )


class TestThePythonExample:
    def test_the_first_snippet_runs_and_says_what_it_claims(self) -> None:
        """`decision.leaves_the_machine # False`, with the comment as the
        assertion. A snippet whose comment disagrees with the code is worse
        than no snippet."""
        from iriguchi import route

        decision = route("Summarise this article.", local=True, external=True)
        assert decision.leaves_the_machine is False
        assert decision.reasons, "the snippet indexes reasons[0]"
        assert decision.reasons[0].detail.strip()

    def test_the_presidio_interop_snippet_still_typechecks_at_runtime(self) -> None:
        """The README tells a Presidio user they can bring results without
        installing anything. That claim is the whole of `interop/`."""
        # Imported the way the README says to. That spelling used to be the one
        # that did not typecheck -- `__getattr__` is annotated `-> object`, so
        # mypy refused to call it -- which is how the missing TYPE_CHECKING
        # re-exports in `iriguchi/__init__.py` were found.
        from iriguchi import findings_from_presidio, route

        findings = findings_from_presidio([{"entity_type": "PERSON", "start": 0, "end": 5}])
        decision = route("Alice, prove the lemma.", findings=findings, local=True, external=True)
        assert not decision.leaves_the_machine


class TestTheSettingsTable:
    """The half that was wrong in a way no example would reveal."""

    def test_every_flag_it_lists_exists(self, readme: str) -> None:
        """`--moderate-at` and `--high-at` were listed as flags and are
        environment variables. A reader who tried them got an argparse error
        from a table that had never been run."""
        # The README documents two programs now -- the CLI and
        # `tools/simulate.py` -- so the set of real flags is the union of both
        # parsers. Checking only the CLI's rejected `--corpus`, which exists and
        # belongs to the other one: a true flag failing a truth test.
        # The top-level parser and every subcommand's, because `--findings` and
        # `--batch` live on `route` and the README documents them in backticks.
        # The first version walked only the top level and passed for as long as
        # the README happened not to backtick a subcommand flag.
        parser = build_parser()
        parsers = [parser] + [
            sub
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for sub in action.choices.values()
        ]
        options = {
            action.option_strings[0]
            for each in parsers
            for action in each._actions
            if action.option_strings
        } | _simulate_flags()
        claimed = set(re.findall(r"`(--[a-z][a-z-]+)`", readme))
        assert claimed, "no flags are documented; this test is guarding nothing"
        assert claimed <= options, (
            f"the README documents flags that do not exist: {claimed - options}"
        )

    def test_every_environment_variable_it_names_is_known(self, readme: str) -> None:
        """The mirror. An `IRIGUCHI_*` key iriguchi does not know is refused at
        startup, so a documented typo is an error somebody hits immediately."""
        from iriguchi.config import IriguchiConfig

        known = {f"IRIGUCHI_{field.upper()}" for field in IriguchiConfig.__dataclass_fields__}
        claimed = set(re.findall(r"\b(IRIGUCHI_[A-Z_]+)\b", readme))
        assert claimed, "no settings are documented; this test is guarding nothing"
        assert claimed <= known, f"the README names unknown settings: {claimed - known}"

    def test_every_scanner_it_offers_is_registered(self, readme: str) -> None:
        """The scanner table is the first thing somebody acts on, and a name
        that is not in the registry is a copy-paste that fails."""
        from iriguchi.infrastructure.registry import SCANNERS

        table = readme.split("| scanner | missed findings")[1].split("\n\n")[0]
        named = set(re.findall(r"\|\s*\*{0,2}`([a-z+]+)`\*{0,2}\s*\|", table))
        assert named, "the scanner table lost its names"
        assert named <= set(SCANNERS.names), f"unregistered scanners offered: {named}"


class TestTheRoadmap:
    """The road table, and the sentence above it.

    That sentence named `iriguchi ask` as its example of *a name in this table
    is a plan, not a command* -- and `ask` had been typeable for some time when
    somebody finally read it. A stale list of commands is the same failure the
    rest of this file exists for, one paragraph further down the page, and it
    survived longer because nothing in the first screen was wrong.
    """

    @staticmethod
    def _listed(readme: str) -> set[str]:
        """The commands the roadmap paragraph claims are built."""
        marker = "The built commands are "
        assert marker in readme, "the README no longer says which commands are built"
        end = "is the authority"
        assert end in readme.split(marker, 1)[1], "the sentence no longer ends where this expects"
        sentence = readme.split(marker, 1)[1].split(end, 1)[0]
        return set(re.findall(r"`([a-z]+)`", sentence))

    @staticmethod
    def _real() -> set[str]:
        [commands] = [
            action
            for action in build_parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        return set(commands.choices)

    def test_it_names_every_command_that_exists(self, readme: str) -> None:
        missing = self._real() - self._listed(readme)
        assert not missing, f"built and unlisted: {sorted(missing)}"

    def test_it_names_nothing_that_does_not(self, readme: str) -> None:
        """The half that was actually wrong. `ask` was listed as unbuildable
        while being built; the mirror of that is a command listed after it is
        removed, and both read the same to somebody skimming."""
        invented = self._listed(readme) - self._real()
        assert not invented, f"listed and not a command: {sorted(invented)}"

    def test_the_table_separates_built_from_reachable(self, readme: str) -> None:
        """ADR-0019's whole content. The external half is built, tested against
        a real mamori, and openable by nobody who is not on this machine -- and
        a single `built` column had no way to say that."""
        assert "| **v0.2** | **yes** | **with a sibling checkout** |" in readme
        assert "0019-the-external-route-needs-a-checkout-nobody-has.md" in readme
