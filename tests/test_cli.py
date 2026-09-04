"""The command line, and the command the project is named after.

Every test here isolates itself: chdir to `tmp_path` and strip `IRIGUCHI_*`. A
CLI test that reads a developer's real environment passes on their machine and
fails in CI, or worse, passes in both for the wrong reason.

The important assertions are the golden ones. An explanation nobody diffs is an
explanation that drifts, and `--explain` is where somebody decides whether to
trust this tool with their work.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest

from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main

SECRET_PROMPT = "この二つを比較して証明してください。連絡先は tanaka@example.com です。"
EASY_PROMPT = "この記事を三行で要約してください。"
HARD_PROMPT = "この二つのアルゴリズムを比較して、計算量を証明してください。"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> Iterator[None]:
    """No real configuration, no real working directory."""
    for key in [k for k in __import__("os").environ if k.startswith("IRIGUCHI_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    yield


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), out=out)
    return code, out.getvalue()


class TestRoute:
    def test_an_easy_harmless_prompt_stays_local(self) -> None:
        code, output = run("--local", "--external", "route", EASY_PROMPT)
        assert code == EXIT_OK
        assert "route        LOCAL" in output

    def test_a_hard_harmless_prompt_leaves(self) -> None:
        code, output = run("--local", "--external", "route", HARD_PROMPT)
        assert code == EXIT_OK
        assert "route        EXTERNAL" in output

    def test_a_hard_prompt_with_an_address_does_not(self) -> None:
        code, output = run("--local", "--external", "route", SECRET_PROMPT)
        assert code == EXIT_OK
        assert "route        LOCAL" in output
        assert "removed" in output

    def test_it_always_says_it_sent_nothing(self) -> None:
        for prompt in (EASY_PROMPT, HARD_PROMPT, SECRET_PROMPT):
            _, output = run("--local", "--external", "route", prompt)
            assert "sent         nothing" in output

    def test_the_prompt_is_never_echoed_back(self) -> None:
        _, output = run("--local", "--external", "route", "--explain", SECRET_PROMPT)
        assert "tanaka@example.com" not in output
        assert "23-41" in output, "the span is printed instead"

    def test_a_prompt_can_come_from_standard_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(SECRET_PROMPT))
        code, output = run("--local", "--external", "route", "-")
        assert code == EXIT_OK
        assert "route        LOCAL" in output


class TestTheGoldenExplanation:
    """The output somebody reads when deciding whether to trust this.

    Asserted whole, not by substring, because the interesting failures are
    things that *disappear* -- a removed section, a reason that stopped being
    printed -- and a substring check cannot see an absence.
    """

    EXPECTED = """\
  route        LOCAL      nothing leaves this machine
  sensitivity  restricted   (1 finding)
  complexity   high   (3 signals)  (two escalating markers)

  reasons
    policy.prefer-local
        complexity band high would have called for the larger model, but the external \
destination is not available

  removed
    external     restricted: 1 finding(s), the first from fallback.email-shape at 23-41; \
not permitted to leave
  sent         nothing

  findings
    fallback.email-shape                23-41  [fallback]

  signals
    complexity.formal-reasoning         weight 0.45  escalating
    complexity.mixed-script             weight 0.20
    complexity.multi-step               weight 0.45  escalating
    score 0.7580"""

    def test_it_reads_exactly_like_this(self) -> None:
        _, output = run("--local", "--external", "route", "--explain", SECRET_PROMPT)
        actual = "\n".join(line.rstrip() for line in output.strip().split("\n"))
        expected = "\n".join(line.rstrip() for line in self.EXPECTED.strip().split("\n"))
        assert actual == expected

    def test_the_reason_does_not_contradict_the_band(self) -> None:
        """The defect the CLI found on its first run.

        Two different situations reach `policy.prefer-local`: complexity did not
        ask to escalate, or it did and there was nowhere to escalate to. They
        had one sentence between them, so a `HIGH` band printed "does not call
        for the larger model" -- a decision explaining itself wrongly, which is
        worse than not explaining.
        """
        _, output = run("--local", "--external", "route", SECRET_PROMPT)
        assert "would have called for the larger model" in output
        assert "does not call for the larger model" not in output


class TestFailClosedAtTheEdge:
    def test_nothing_configured_refuses(self) -> None:
        code, output = run("route", EASY_PROMPT)
        assert code == EXIT_REFUSED
        assert "route        REFUSED" in output

    def test_a_refusal_is_not_a_crash(self) -> None:
        """Distinct exit codes, because a caller that cannot tell a refusal from
        a failure will retry the refusal forever."""
        refused, _ = run("route", SECRET_PROMPT)
        worked, _ = run("--local", "route", SECRET_PROMPT)
        assert refused == EXIT_REFUSED
        assert worked == EXIT_OK
        assert EXIT_REFUSED != EXIT_ERROR

    def test_a_restricted_prompt_with_only_an_external_route_is_refused(self) -> None:
        code, output = run("--external", "--no-local", "route", SECRET_PROMPT)
        assert code == EXIT_REFUSED
        assert "sent         nothing" in output


class TestConfiguration:
    def test_flags_beat_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "0")
        code, _ = run("--local", "route", EASY_PROMPT)
        assert code == EXIT_OK

    def test_the_environment_is_read_when_no_flag_is_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "yes")
        code, _ = run("route", EASY_PROMPT)
        assert code == EXIT_OK

    def test_an_unknown_setting_is_refused_rather_than_ignored(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A typo that silently does nothing is the worst available outcome."""
        monkeypatch.setenv("IRIGUCHI_LOCALL", "1")
        code, _ = run("route", EASY_PROMPT)
        assert code == EXIT_ERROR
        assert "unknown settings" in capsys.readouterr().err

    def test_a_value_that_is_neither_yes_nor_no_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "maybe")
        code, _ = run("route", EASY_PROMPT)
        assert code == EXIT_ERROR
        assert "not a yes or a no" in capsys.readouterr().err

    def test_both_destinations_default_to_off(self) -> None:
        """The fail-safe value. Somebody who has configured nothing gets
        refusals, not a router assuming a model exists."""
        _, output = run("config")
        assert "not configured" in output
        assert "every prompt is refused" in output


class TestDoctor:
    def test_it_says_what_a_missing_local_model_costs(self) -> None:
        _, output = run("--external", "doctor")
        assert "every prompt containing anything sensitive is refused" in output

    def test_it_says_what_the_built_in_scanner_misses(self) -> None:
        """Somebody has to be told, and the tool is the only thing they run.

        Keyed on the measured rate rather than on a phrase. The phrase version
        of this assertion passed on a machine with mamori installed -- where
        `doctor` takes a different branch entirely -- and failed in CI, which is
        where mamori is absent and where the sentence actually renders.

        `doctor` has three branches here and this exercise reaches whichever one
        the environment produces, so the assertion has to be about what every
        branch owes the reader: the cost, and a scanner that would fix it.
        """
        _, output = run("--local", "--external", "doctor")
        assert "63.5%" in output or "installed but not selected" in output, output
        assert "mamori" in output


class TestEval:
    def test_it_runs_the_corpus_and_reports(self) -> None:
        code, output = run("--local", "--external", "eval")
        assert code == EXIT_OK
        assert "missed findings" in output
        assert "leak rate" in output

    def test_it_can_report_one_source(self) -> None:
        _, output = run("--local", "--external", "eval", "--source", "generated")
        assert "cases                21" in output

    def test_an_unknown_source_is_an_error_rather_than_an_empty_table(self) -> None:
        code, output = run("--local", "--external", "eval", "--source", "nope")
        assert code == EXIT_ERROR
        assert "no cases from source" in output


class TestDemo:
    def test_it_shows_both_axes_and_the_trap_between_them(self) -> None:
        code, output = run("--local", "--external", "demo")
        assert code == EXIT_OK
        assert "route        LOCAL" in output
        assert "route        EXTERNAL" in output
        assert output.count("sent         nothing") == 3


class TestNothingLeaves:
    """The whole suite runs with `socket.socket` poisoned by conftest.py, so
    every test above is already evidence. This says so where somebody looking
    for the guarantee would look."""

    def test_every_command_completes_with_no_network(self) -> None:
        for argv in (
            ["--local", "--external", "route", "--dry-run", SECRET_PROMPT],
            ["config"],
            ["doctor"],
            ["--local", "--external", "demo"],
            ["--local", "--external", "eval"],
        ):
            code, _ = run(*argv)
            assert code in (EXIT_OK, EXIT_REFUSED)

    def test_the_dry_run_flag_is_accepted(self) -> None:
        """It changes nothing today, and it has to keep meaning something.

        v0.2 adds an outbound path in `ask`. `route` must still send nothing,
        and this flag is where that promise is written down.
        """
        with_flag, a = run("--local", "--external", "route", "--dry-run", SECRET_PROMPT)
        without, b = run("--local", "--external", "route", SECRET_PROMPT)
        assert with_flag == without
        assert a == b


class TestWhatConfigSays:
    """`config` is prose, not a dump. Somebody should be able to answer "can
    anything leave this machine" from it without reading the codebase."""

    def test_local_only(self) -> None:
        _, output = run("--local", "--no-external", "config")
        assert "Nothing can leave this machine" in output

    def test_external_only_says_the_refusal_is_intended(self) -> None:
        _, output = run("--no-local", "--external", "config")
        assert "not a fallback" in output

    def test_both_describes_the_trade(self) -> None:
        _, output = run("--local", "--external", "config")
        assert "A prompt with a finding stays, whatever its difficulty." in output


class TestTheExplanationWithNothingToExplain:
    """A clear, easy prompt still renders every section.

    An `--explain` that silently drops its headings when there is nothing under
    them makes an empty result indistinguishable from a broken one.
    """

    def test_it_says_none_rather_than_omitting_the_section(self) -> None:
        _, output = run("--local", "--external", "route", "--explain", EASY_PROMPT)
        assert "  findings\n    none" in output
        assert "  signals\n    none" in output
        assert "removed      nothing" in output

    def test_a_reason_from_an_unrecognised_source_still_prints(self) -> None:
        """`render` orders known sources by hand and everything else after them.

        A future adapter that nobody remembered to add to that list must still
        appear, at the end, rather than crashing the explanation it belongs to.
        """
        from iriguchi.interfaces.cli.render import _source_rank

        assert _source_rank("routing") < _source_rank("policy")
        assert _source_rank("policy") < _source_rank("something-new")


class TestTheScannerFlagIsActuallyUsed:
    """`--scanner` was accepted by the parser and dropped by the merge.

    Found while measuring: `iriguchi --scanner fallback+presidio eval` printed
    **63.5% missed findings**, which is the built-in fallback's number. The flag
    parsed, validated against the registry's `choices`, and then `_config`
    reduced the whole of it to::

        use_mamori=args.scanner == "mamori"

    so every name except `mamori` was silently replaced by the default. A user
    who selected a scanner got a different one, with nothing said -- which is
    the exact outcome the registry's own refusal message calls *the worst
    available*, promised in one module and broken in another.

    The sharpest part is that `_config`'s docstring is about this bug. It
    explains that `replace` was chosen over a constructor call because the
    constructor "listed the three fields that existed when it was written, so
    every field added afterwards would have been read from the environment and
    then silently dropped". The flag was added afterwards and silently dropped.
    """

    @staticmethod
    def _config_for(*argv: str) -> object:
        from iriguchi.interfaces.cli.main import _config, build_parser

        return _config(build_parser().parse_args(list(argv)))

    def test_the_name_reaches_the_configuration(self) -> None:
        assert self._config_for("--scanner", "fallback", "config").scanner == "fallback"  # type: ignore[attr-defined]

    @pytest.mark.parametrize("name", ["fallback", "presidio", "fallback+presidio", "mamori"])
    def test_every_registered_name_survives_the_merge(self, name: str) -> None:
        """Parametrized over the registry's own names rather than over a list
        typed here, so a scanner added later is covered by this without anybody
        remembering to come back."""
        from iriguchi.infrastructure.registry import SCANNERS

        assert name in SCANNERS, f"{name} is not registered; this test is guarding nothing"
        config = self._config_for("--scanner", name, "config")
        assert config.scanner_name() == name, (  # type: ignore[attr-defined]
            f"--scanner {name} produced {config.scanner_name()!r}"  # type: ignore[attr-defined]
        )

    def test_no_flag_leaves_the_environment_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The other half of the same defect. A merge that writes a field
        unconditionally overwrites whatever the environment said."""
        monkeypatch.setenv("IRIGUCHI_SCANNER", "fallback")
        assert self._config_for("config").scanner == "fallback"  # type: ignore[attr-defined]

    def test_a_flag_beats_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IRIGUCHI_SCANNER", "fallback")
        assert self._config_for("--scanner", "mamori", "config").scanner_name() == "mamori"  # type: ignore[attr-defined]

    @pytest.mark.parametrize("command", ["config", "doctor", "algorithms"])
    def test_every_surface_names_the_same_scanner(self, command: str) -> None:
        """The expression `"mamori" if use_mamori else (scanner or default)` was
        written out **four times** -- twice in `config.py`, twice in the CLI --
        and the CLI's merge fed three of them a value it had thrown away. Four
        copies of *which algorithm did the user pick* is how a flag comes to be
        accepted and ignored.

        There is one copy now, and this is what notices if a fifth appears: a
        surface that disagrees with the others about what is selected.
        """
        import io

        from iriguchi.interfaces.cli.main import main

        out = io.StringIO()
        main(["--local", "--scanner", "fallback", command], out=out)
        report = out.getvalue()
        assert "fallback" in report
        # `presidio` is registered and not selected. A surface reading a stale
        # field would show the default, so this only passes if the flag landed.
        selected = self._config_for("--scanner", "presidio", command)
        assert selected.scanner_name() == "presidio", command  # type: ignore[attr-defined]
