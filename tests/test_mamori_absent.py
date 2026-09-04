"""iriguchi with mamori genuinely unimportable.

This is the test the `mamori-is-an-adapter` contract cannot be. That contract
sees a transitive path -- `interfaces -> config -> mamori_scanner -> mamori` --
and it is right that the path exists; what it cannot see is that every
`import mamori` in the adapter is inside a function, so importing the module
does not require the package. Two edges are therefore ignored in
`.importlinter`, and the guarantee they were protecting is asserted here
instead, where it can be asserted for real.

`ImportBlocker` makes `import mamori` raise, the way it would on a machine that
never installed it. Then the whole CLI runs.

The `zero runtime dependencies` CI job is the other half: it installs the wheel
with no extras into a clean environment, so there is genuinely no mamori there,
and runs these same commands.
"""

from __future__ import annotations

import builtins
import importlib.util
import io
import sys
from collections.abc import Iterator, Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

import pytest

from iriguchi.errors import ScanError
from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main


class ImportBlocker:
    """Simulates one of two environments, and they are not the same environment.

    `mamori_state()` separates *absent* from *installed and will not import*,
    because a test gate must skip on the first and fail on the second. This
    double has to be able to produce both, and the first version of this file
    could only produce the second -- it blocked the import and left `find_spec`
    finding the package, then called the result "absent". The classification
    change is what surfaced that.

    - `absent`: `find_spec` finds nothing and the import fails. A machine that
      never installed mamori.
    - `broken`: `find_spec` finds it and the import fails. A machine where
      something is wrong with an install somebody meant to have working.

    Both restore what they touched. Clearing `sys.modules` matters as much as
    blocking the import: anything already imported never reaches a hook.
    """

    def __init__(self, mode: str, name: str = "mamori") -> None:
        assert mode in {"absent", "broken"}
        self.mode = mode
        self.name = name
        self._saved: dict[str, ModuleType] = {}
        self._real_import = builtins.__import__
        self._real_find_spec = importlib.util.find_spec

    def __enter__(self) -> ImportBlocker:
        self._saved = {
            key: module
            for key, module in sys.modules.items()
            if key == self.name or key.startswith(f"{self.name}.")
        }
        for key in self._saved:
            del sys.modules[key]

        def blocked(name: str, *args: Any, **kwargs: Any) -> ModuleType:
            if name == self.name or name.startswith(f"{self.name}."):
                raise ImportError(f"No module named {self.name!r}")
            return self._real_import(name, *args, **kwargs)

        builtins.__import__ = blocked

        # `find_spec` is patched in *both* modes, in opposite directions, so
        # that neither depends on whether mamori happens to be installed on the
        # machine running the tests. A developer has it and CI does not; without
        # this, `absent` was untestable on one and `broken` on the other, and
        # four tests failed the first time this ran in a mamori-free
        # environment.
        #
        # The unfaked version of `absent` is the CI job that installs the wheel
        # with no extras. There is no unfaked version of `broken`, which is
        # the point of having a double at all.
        answer = None if self.mode == "absent" else ModuleSpec(self.name, loader=None)

        def spec_for(name: str, package: str | None = None) -> Any:
            if name == self.name or name.startswith(f"{self.name}."):
                return answer
            return self._real_find_spec(name, package)

        importlib.util.find_spec = spec_for
        return self

    def __exit__(self, *exc: object) -> None:
        builtins.__import__ = self._real_import
        importlib.util.find_spec = self._real_find_spec
        sys.modules.update(self._saved)


@pytest.fixture
def without_mamori() -> Iterator[None]:
    """A machine that never installed it."""
    with ImportBlocker("absent"):
        yield


@pytest.fixture
def broken_mamori() -> Iterator[None]:
    """A machine where the install is there and does not work."""
    with ImportBlocker("broken"):
        yield


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> Iterator[None]:
    import os

    for key in [k for k in os.environ if k.startswith("IRIGUCHI_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    yield


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return main(list(argv), out=out), out.getvalue()


class TestTheBlockerBlocks:
    """A test double nobody has seen work is a test double that proves nothing."""

    def test_mamori_imports_normally_outside_the_context(self) -> None:
        pytest.importorskip("mamori")
        import mamori  # noqa: F401

    def test_and_not_inside_it(self, without_mamori: None) -> None:
        with pytest.raises(ImportError, match="mamori"):
            import mamori  # noqa: F401

    def test_availability_reports_false(self, without_mamori: None) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import mamori_is_available

        assert mamori_is_available() is False


class TestEverythingStillWorks:
    """The promise: a person who wants only a router gets one."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["--local", "--external", "route", "田中さんに tanaka@example.com で連絡"],
            ["--local", "--external", "route", "--explain", "--dry-run", "hello"],
            ["config"],
            ["doctor"],
            ["--local", "--external", "demo"],
            ["--local", "--external", "eval"],
        ],
        ids=["route", "explain", "config", "doctor", "demo", "eval"],
    )
    def test_a_command_runs(self, without_mamori: None, argv: Sequence[str]) -> None:
        code, output = run(*argv)
        assert code in (EXIT_OK, EXIT_REFUSED)
        assert output

    def test_the_fallback_scanner_is_what_answers(self, without_mamori: None) -> None:
        _, output = run("--local", "--external", "route", "--explain", "田中さんへ")
        assert "fallback." in output
        assert "mamori." not in output

    def test_doctor_says_mamori_is_missing_and_what_that_costs(self, without_mamori: None) -> None:
        """The cost as a number, and a remedy that can be run.

        This used to grep the sentence `misses names without an honorific`,
        which broke the day the sentence was reworded to lead with the measured
        rate -- a test about phrasing rather than about what the reader is told.

        What has to hold is: the miss rate is stated, and the fix offered is one
        that exists. For as long as mamori was the only better scanner, `doctor`
        named a 63.5% miss rate and pointed at a package that is not on PyPI.
        """
        _, output = run("doctor")
        assert "mamori is not installed" in output
        assert "63.5%" in output, "doctor no longer says what the fallback costs"
        assert "presidio" in output, "doctor offers no remedy a reader can install"

    def test_the_corpus_still_loads(self, without_mamori: None) -> None:
        """The 134 borrowed cases are committed fixtures, not read from mamori.

        If this ever fails, somebody has made `evaluation/` reach into an
        installed package -- which is the thing `tools/borrow_mamori_cases.py`
        exists to avoid.
        """
        _, output = run("--local", "--external", "eval")
        assert "cases                155" in output


class TestAskingForItAnywayIsRefused:
    def test_selecting_mamori_without_mamori_is_an_error(
        self, without_mamori: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Not a silent downgrade to the fallback.

        Somebody who passed `--scanner mamori` is relying on it finding what the
        fallback cannot. Handing them the fallback instead, quietly, is the
        worst available outcome: they would believe they had tightened something
        and would have loosened it.
        """
        code, _ = run("--local", "--external", "--scanner", "mamori", "route", "hello")
        assert code == EXIT_ERROR
        assert "mamori is not installed" in capsys.readouterr().err

    def test_the_error_says_how_to_install_it(self, without_mamori: None) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import MamoriScanner

        with pytest.raises(ScanError, match="uv pip install"):
            MamoriScanner()


class TestBrokenIsNotAbsent:
    """The distinction the classification exists for.

    A sibling that is installed and will not import is somebody's environment
    being wrong, and it must not be reported, handled or gated as though the
    sibling had simply never been installed. akashi found this class of bug in
    its drift check, where an `HTTPError` was swallowed as a connection failure
    and a 404 passed as "cannot reach".
    """

    def test_the_two_environments_classify_differently(self) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state

        with ImportBlocker("absent"):
            assert mamori_state()[0] is SiblingState.ABSENT
        with ImportBlocker("broken"):
            assert mamori_state()[0] is SiblingState.BROKEN

    def test_a_broken_install_is_not_reported_as_missing(self, broken_mamori: None) -> None:
        """The `policy.prefer-local` mistake again, and the reason this was worth
        fixing rather than noting: the old message told somebody to install what
        they already had, which sends them to fix the wrong thing."""
        from iriguchi.infrastructure.scanners.mamori_scanner import MamoriScanner

        with pytest.raises(ScanError, match="installed and cannot be imported"):
            MamoriScanner()

    def test_doctor_says_broken_rather_than_missing(self, broken_mamori: None) -> None:
        _, output = run("doctor")
        assert "will not import" in output
        assert "mamori is not installed" not in output

    def test_the_fallback_still_answers(self, broken_mamori: None) -> None:
        """A broken sibling costs the upgrade, not the tool."""
        code, output = run("--local", "--external", "route", "田中さんへ")
        assert code == EXIT_OK
        assert "fallback." in output

    def test_but_asking_for_it_explicitly_still_refuses(self, broken_mamori: None) -> None:
        code, _ = run("--local", "--external", "--scanner", "mamori", "route", "hello")
        assert code == EXIT_ERROR


class TestTheGateWouldHaveGoneQuiet:
    """What the old gate did, kept as a test so the fix cannot be undone silently.

    `tests/test_mamori_scanner.py` is the only place the mamori boundary is
    checked. Gated on a boolean that was false for both environments, the whole
    file disappeared when mamori was *broken* -- and the build went green at the
    moment the boundary had moved.
    """

    def test_availability_alone_cannot_tell_them_apart(self) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import mamori_is_available

        with ImportBlocker("absent"):
            absent = mamori_is_available()
        with ImportBlocker("broken"):
            broken = mamori_is_available()
        assert absent == broken is False, (
            "a boolean is the right answer for `doctor`, which asks whether mamori "
            "can be used -- and the wrong one for a test gate, which has to skip on "
            "one of these and fail on the other"
        )

    def test_the_seam_suite_skips_on_absent_and_not_on_broken(self) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState

        with ImportBlocker("absent"):
            from iriguchi.infrastructure.scanners.mamori_scanner import mamori_state

            assert mamori_state()[0] is SiblingState.ABSENT, "the suite skips here"
        with ImportBlocker("broken"):
            state, detail = mamori_state()
            assert state is SiblingState.BROKEN, "the suite runs and fails here"
            assert detail, "and says why"


class TestLookingForItCanItselfFail:
    """`find_spec` raises on its own account, and that is not absence either.

    A broken path entry, a finder that objects, a namespace package whose parent
    is missing. Rare, and the same reasoning applies: something is wrong with an
    environment somebody meant to work, so it is a finding rather than a skip.
    """

    @pytest.mark.parametrize("failure", [ImportError("bad finder"), ValueError("__spec__ is None")])
    def test_it_classifies_as_broken(
        self, monkeypatch: pytest.MonkeyPatch, failure: Exception
    ) -> None:
        from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state

        def raising(name: str, package: str | None = None) -> None:
            raise failure

        monkeypatch.setattr("importlib.util.find_spec", raising)
        state, detail = mamori_state()
        assert state is SiblingState.BROKEN
        assert "looking for mamori failed" in detail


class TestAvailableHasToMeanYouCanUseIt:
    """Measured against a wheel in a clean venv, which is what a user has.

    `iriguchi doctor` with `EXTERNAL=1`, a real URL and a real model printed::

        external service  available    some-model at https://example.invalid/v1

    and every `ask --external` against that configuration is refused, because
    `MamoriChannel.__init__` finds no mamori and there is no unprotected
    fallback. The word was wrong in the one place a person checks before
    trusting the setup.

    `_endpoint` already avoids this defect for a missing endpoint -- its own
    docstring names it, *a true sentence that sends the reader to fix the wrong
    thing* -- and did not check the other thing `ask` requires. The two are not
    interchangeable, either: a missing endpoint is two environment variables
    away, and missing protection is a package that **is not on PyPI**, so a
    reader who conflates them goes looking for a fix that does not exist.
    """

    @staticmethod
    def _describe() -> str:
        from iriguchi.config import IriguchiConfig

        return IriguchiConfig(
            external=True,
            external_url="https://example.invalid/v1",
            external_model="some-model",
        ).describe()

    @staticmethod
    def _external_line(report: str) -> str:
        return next(line for line in report.splitlines() if line.startswith("external service"))

    def test_it_does_not_read_as_a_destination_you_can_ask(self, without_mamori: None) -> None:
        """Not *the word `available` is absent* -- that was the first version of
        this test and it was about a word rather than about a claim. `available
        for routing` is true with no mamori, because routing does work.

        What must not appear is the rendering that means **you can send to
        this**: the model and the URL sitting after `available` with nothing
        qualifying them."""
        external = self._external_line(self._describe())
        assert "some-model at" not in external, external
        assert "for routing" in external, external

    def test_the_line_says_which_thing_is_missing(self, without_mamori: None) -> None:
        """Two different blockers render two different lines. One `unavailable`
        covering both would send half the readers to the wrong fix."""
        external = self._external_line(self._describe())
        assert "protect" in external, external
        assert "endpoint" not in external, external

    def test_it_says_what_is_missing(self, without_mamori: None) -> None:
        """About the external service specifically. The scanner line has
        mentioned mamori all along, and a report where the only explanation sits
        beside a different setting is a report somebody reads past."""
        report = self._describe()
        assert "external service cannot be used" in report, report
        assert "mamori" in report

    def test_it_says_routing_and_asking_will_disagree(self, without_mamori: None) -> None:
        """`route` will happily say a prompt may leave. Somebody who tests with
        `route` and deploys with `ask` finds out at the wrong moment."""
        report = self._describe()
        assert "`route` still decides" in report, report

    def test_it_does_not_send_the_reader_after_the_endpoint(self, without_mamori: None) -> None:
        """The endpoint is set. Telling somebody to set `EXTERNAL_URL` here is
        the wrong-fix defect with a different subject."""
        report = self._describe()
        assert f"{'IRIGUCHI_'}EXTERNAL_URL" not in report, report

    def test_broken_is_still_not_absent(self, broken_mamori: None) -> None:
        """The distinction the whole module exists for, kept in the report.
        Telling somebody to install what they already have is the defect
        pointing the opposite way."""
        report = self._describe()
        assert "not installed" not in report, report

    def test_with_mamori_present_it_is_available_again(self) -> None:
        """A floor. The three assertions above pass against a report that says
        nothing is ever available, which would be a worse bug than the one being
        fixed."""
        from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state

        if mamori_state()[0] is not SiblingState.AVAILABLE:
            pytest.skip("mamori is not importable here; the positive case cannot be shown")
        external = self._external_line(self._describe())
        assert "some-model at" in external, external

    def test_the_command_itself_shows_it(self, without_mamori: None) -> None:
        """Through `doctor`, because the command is what somebody ran."""
        import os

        os.environ["IRIGUCHI_EXTERNAL"] = "1"
        os.environ["IRIGUCHI_EXTERNAL_URL"] = "https://example.invalid/v1"
        os.environ["IRIGUCHI_EXTERNAL_MODEL"] = "some-model"
        code, report = run("doctor")
        assert code == EXIT_OK
        external = self._external_line(report)
        assert "some-model at" not in external, external
        assert "protect" in external, external


class TestAdviceSomebodyCanFollow:
    """Every sentence that tells a reader to install mamori says it is not on PyPI.

    `mamori` is a 404 on PyPI. iriguchi's remedy was `uv pip install -e
    ../mamori` -- a relative path that resolves on a machine with both checkouts
    side by side, which is one machine. A reader who has never seen this layout
    reads that as a typo for a package name, tries `pip install mamori`, and
    concludes the advice is stale rather than that the package is unpublished.

    The comment above `_MISSING` had said *not on PyPI yet, so the instruction
    is a checkout rather than a package name* since it was written. **The string
    somebody actually reads did not.** A true fact in a comment is a fact the
    user never gets.

    Collected from the constants rather than grepped out of the files, so a
    reflowed line does not fail this and a fourth message does not slip past it.
    """

    @staticmethod
    def _remedies() -> dict[str, str]:
        from iriguchi.infrastructure.registry import SCANNERS
        from iriguchi.infrastructure.scanners.mamori_scanner import _MISSING

        with ImportBlocker("absent"):
            _, from_registry = SCANNERS.describe("mamori").available()
            try:
                from iriguchi.infrastructure.channels.mamori_channel import MamoriChannel

                MamoriChannel()
            except Exception as refusal:
                from_channel = str(refusal)
            else:  # pragma: no cover - reached only if the refusal stops working
                from_channel = ""
        return {"scanner": _MISSING, "registry": from_registry, "channel": from_channel}

    def test_there_are_three_of_them(self) -> None:
        """A floor. The parametrized assertions below all pass over an empty
        set, and the point of collecting them is to catch a fourth."""
        remedies = self._remedies()
        assert len(remedies) == 3
        assert all(remedies.values()), remedies

    @pytest.mark.parametrize("where", ["scanner", "registry", "channel"])
    def test_it_says_the_package_is_not_published(self, where: str) -> None:
        message = self._remedies()[where]
        assert "not on PyPI" in message, message

    @pytest.mark.parametrize("where", ["scanner", "registry", "channel"])
    def test_it_still_says_what_to_do_instead(self, where: str) -> None:
        """Naming the problem without naming the fix would be the opposite
        failure: a reader who now knows they are stuck and not how to proceed."""
        message = self._remedies()[where]
        assert "checkout" in message and "../mamori" in message, message
