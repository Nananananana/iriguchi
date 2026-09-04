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
        options = {
            action.option_strings[0] for action in build_parser()._actions if action.option_strings
        }
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
