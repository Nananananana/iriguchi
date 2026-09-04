"""A refusal is the one answer where the working *is* the answer.

The complaint, and it is fair: a tool that replies "there is nothing I can tell
you" is a tool people stop running. iriguchi's refusals were not empty -- they
carried the reason -- but everything else it had learned was compressed into two
integers:

      route        REFUSED    nothing runs
      sensitivity  restricted   (2 findings)
      complexity   high   (3 signals)

*It found two things and will not say which, and there is nothing else.* The
findings and signals were already computed and sat behind `--explain`, a flag
somebody who just got refused has no reason to know about.

Two changes, and the reasoning for both is the same. When the router does what
was asked, the answer is the point and the working is optional. **When it
refuses, the working is all there is** -- so it is printed, and it is followed
by the settings that would have produced an answer instead.

Neither change weakens anything. The detail carries rule ids and spans and never
a matched value (ADR-0006), and the guidance names destinations, never a way to
scan less.
"""

from __future__ import annotations

import io

import pytest

from iriguchi.interfaces.cli.main import EXIT_OK, EXIT_REFUSED, main

#: Findings on both axes, so a refusal has something to show. Invented, as the
#: corpus rules require.
LOADED = "田中さんの連絡先 tanaka@example.com を使って、二つの案を比較し証明してください。"


@pytest.fixture(autouse=True)
def nothing_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("IRIGUCHI_LOCAL", "IRIGUCHI_EXTERNAL"):
        monkeypatch.delenv(key, raising=False)


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return main(list(argv), out=out), out.getvalue()


class TestARefusalCarriesTheEvidence:
    def test_it_is_a_refusal_to_begin_with(self) -> None:
        """The premise. With a destination available this whole file is about
        a branch that never runs."""
        code, _ = run("route", LOADED)
        assert code == EXIT_REFUSED

    def test_the_findings_are_listed_and_not_counted(self) -> None:
        code, output = run("route", LOADED)
        assert code == EXIT_REFUSED
        assert "fallback.email-shape" in output
        assert "fallback.japanese-honorific" in output

    def test_the_signals_are_listed_with_their_weights(self) -> None:
        """A reader who disagrees with the band needs to see which markers
        produced it, and what each was worth."""
        _, output = run("route", LOADED)
        assert "complexity.multi-step" in output
        assert "weight" in output

    def test_the_score_is_shown(self) -> None:
        """The number the band came from. A band with no score beside it is a
        verdict with the arithmetic removed."""
        _, output = run("route", LOADED)
        assert "score" in output

    def test_explain_adds_nothing_a_refusal_did_not_already_give(self) -> None:
        """The flag becomes redundant here rather than sometimes-necessary. If
        these ever diverge, somebody has put detail back behind the flag."""
        _, plain = run("route", LOADED)
        _, explained = run("route", "--explain", LOADED)
        assert plain == explained

    def test_no_matched_value_reaches_the_output(self) -> None:
        """The detail is spans and rule ids. ADR-0006 does not get an exception
        because the router was being helpful."""
        _, output = run("route", LOADED)
        for value in ("tanaka@example.com", "田中"):
            assert value not in output, value


class TestASuccessIsStillASummary:
    """The change is about refusals, and only about refusals.

    A decision that answered has an answer to lead with, and printing twenty
    lines of working above it would bury the thing the reader came for.
    """

    def test_a_permitted_route_still_counts_rather_than_lists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        code, output = run("route", LOADED)
        assert code == EXIT_OK
        assert "fallback.email-shape" not in output
        assert "finding" in output

    def test_and_explain_still_adds_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The floor for the test above: `--explain` must still do something,
        or that assertion is passing because the detail was deleted."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        _, output = run("route", "--explain", LOADED)
        assert "fallback.email-shape" in output


class TestItSaysWhatWouldChangeIt:
    def test_it_names_the_missing_settings(self) -> None:
        """A refusal that names the obstacle and not the remedy is a dead end
        wearing an explanation."""
        _, output = run("route", LOADED)
        assert "IRIGUCHI_LOCAL=1" in output
        assert "IRIGUCHI_EXTERNAL=1" in output

    def test_it_names_only_the_ones_that_are_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Telling somebody to set what they have already set is how a reader
        learns to skip the whole block."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.delenv("IRIGUCHI_EXTERNAL", raising=False)
        # A prompt with no findings, so the refusal is about destinations only.
        _, output = run("route", "Summarise this.")
        assert "IRIGUCHI_LOCAL=1" not in output

    def test_it_never_suggests_scanning_less(self) -> None:
        """The one remedy that must never appear. Every other tool in this space
        has a *lower the threshold* setting, and this project's whole argument is
        that a leak rate you can tune is a leak rate somebody tunes."""
        _, output = run("route", LOADED)
        for suggestion in ("--scanner none", "disable", "turn off", "lower the"):
            assert suggestion not in output.lower(), suggestion

    def test_nothing_is_printed_when_a_destination_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        _, output = run("route", "Summarise this.")
        assert "what would change this" not in output

    def test_the_json_form_is_untouched(self) -> None:
        """The contract is frozen at v1 and this is a presentation change. A
        consumer parsing `--json` must see exactly what it saw before."""
        import json

        code, output = run("route", "--json", LOADED)
        assert code == EXIT_REFUSED
        document = json.loads(output)
        assert document["route"] == "refused"
        assert "what would change this" not in output
