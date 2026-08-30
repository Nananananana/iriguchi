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
import io
import sys
from collections.abc import Iterator, Sequence
from types import ModuleType
from typing import Any

import pytest

from iriguchi.errors import ScanError
from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main


class ImportBlocker:
    """Makes `import mamori` fail, and puts everything back afterwards.

    Both halves are needed. Blocking the import is not enough on its own,
    because anything that already imported mamori has it in `sys.modules` and
    would never reach the import hook.
    """

    def __init__(self, name: str = "mamori") -> None:
        self.name = name
        self._saved: dict[str, ModuleType] = {}
        self._real_import = builtins.__import__

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
        return self

    def __exit__(self, *exc: object) -> None:
        builtins.__import__ = self._real_import
        sys.modules.update(self._saved)


@pytest.fixture
def without_mamori() -> Iterator[None]:
    with ImportBlocker():
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
        _, output = run("doctor")
        assert "mamori is not installed" in output
        assert "misses names without an honorific" in output

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
