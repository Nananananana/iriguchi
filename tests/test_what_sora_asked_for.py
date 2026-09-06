"""What the orchestration layer asked for, and what asking revealed.

Sora (`iriguchi-work/05_sora_requirements.md`) calls `route --json` once per
conversation turn and once per card, with a 300 ms budget, and pipes the
rendered prompt through standard input because putting it in `argv` leaves it in
shell history and hits Windows' command-line limit. Six requests came in. Four
were already true or are true now; two are deferred with reasons in the reply.

Testing them turned up three defects nobody had asked about:

**Standard input was decoded in the console's code page.** On a Windows machine
without `PYTHONUTF8`, Japanese piped into `route --json -` came through as
cp932, the honorific finding **vanished**, and the email span shifted by four.
A veto miss caused by an encoding default. Sora's requirement said "UTF-8" in one
word; this is why it had to.

**`python -m iriguchi` did not exist.** The first startup benchmark measured it,
got 100 ms, and reported a number for a command that had failed to run.

**`route` paid for an HTTP client it never opens.** `config.py` imported the
model adapter eagerly, which imported `urllib.request`, `http.client` and
`email.parser` -- about 60 ms of a 270 ms call, on the command that decides and
sends nothing. Lazy now: 215 ms, of which 82 ms is the interpreter.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from iriguchi.interfaces.cli.main import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def both_destinations(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in [k for k in os.environ if k.startswith("IRIGUCHI_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
    monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")


class _Stdin(io.TextIOWrapper):
    """A stand-in for a real console stream: text on top, bytes underneath."""

    def __init__(self, data: bytes) -> None:
        super().__init__(io.BytesIO(data), encoding="utf-8")


def _run(argv: list[str], stdin: bytes | None = None) -> tuple[int, str]:
    """Exit code, and everything the command printed on either stream.

    Decisions go to `out`; a refusal to run (`iriguchi: ...`) goes to stderr,
    the way a command-line tool separates its product from its complaints. A
    test about the complaint has to read the stream it was sent to, so both are
    returned together.
    """
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    real = sys.stdin
    if stdin is not None:
        sys.stdin = _Stdin(stdin)
    try:
        with contextlib.redirect_stderr(err):
            code = main(argv, out=out)
    finally:
        sys.stdin = real
    return code, out.getvalue() + err.getvalue()


def _doc(text: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(text)
    return document


class TestStandardInputIsUtf8WhateverTheConsoleSays:
    """R1. Already implemented as `-`; the acceptance said UTF-8, and it was not."""

    JAPANESE = "田中さんに tanaka@example.com で連絡してください。"

    def test_the_findings_land_on_the_right_characters(self) -> None:
        """Both findings, at code-point offsets into the text as sent. Under
        cp932 the honorific vanished and the email moved to 10-28."""
        code, out = _run(["route", "--json", "-"], self.JAPANESE.encode("utf-8"))
        assert code == EXIT_OK
        spans = [
            (f["rule"], (f["span"]["start"], f["span"]["end"]))
            for f in _doc(out)["sensitivity"]["findings"]
        ]
        assert spans == [
            ("fallback.japanese-honorific", (0, 4)),
            ("fallback.email-shape", (6, 24)),
        ]

    def test_bytes_that_are_not_utf8_are_refused_not_guessed(self) -> None:
        """A replacement character at offset 12 is a span into text nobody sent."""
        code, out = _run(["route", "--json", "-"], self.JAPANESE.encode("cp932"))
        assert code == EXIT_ERROR
        assert "not valid UTF-8" in out

    def test_a_text_only_stream_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The fallback exists for a `StringIO` handed in by a test, never for a
        person: every stdin a process is given has bytes underneath. This is
        the test that keeps the older suite's fixtures working."""
        monkeypatch.setattr(sys, "stdin", io.StringIO("Summarise this."))
        code, out = _run(["route", "--json", "-"])
        assert code == EXIT_OK
        assert _doc(out)["route"] == "local"


class TestPythonDashM:
    def test_the_module_is_executable(self) -> None:
        """Measured failing before it existed: the benchmark reported 100 ms for
        a command that had not run. Real process, real interpreter, so the thing
        being tested is the thing Sora would spawn."""
        result = subprocess.run(
            [sys.executable, "-m", "iriguchi", "route", "--json", "-"],
            input=b"hello",
            capture_output=True,
            env={"IRIGUCHI_LOCAL": "1", "PYTHONUTF8": "1", "PATH": "", "SYSTEMROOT": "C:\\Windows"},
            cwd=REPO / "src",
        )
        assert result.returncode == EXIT_OK, result.stderr.decode(errors="replace")
        assert json.loads(result.stdout)["contract"] == "iriguchi.routing-decision/1"


class TestRouteDoesNotPayForTheHttpClient:
    """R4's number. The interpreter is the floor; this is the part above it."""

    def test_importing_config_does_not_import_the_network_stack(self) -> None:
        """In a fresh interpreter, so this process's already-loaded modules do
        not flatter the result. `urllib.request` costs ~45 ms and `route` never
        opens a connection."""
        probe = (
            "import sys, iriguchi.config, iriguchi.interfaces.cli.main;"
            "print(sorted(m for m in ('urllib.request','http.client','email.parser')"
            " if m in sys.modules))"
        )
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            cwd=REPO / "src",
            env={"PYTHONUTF8": "1", "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]", result.stdout

    def test_the_adapters_are_still_reachable_when_asked_for(self) -> None:
        """The floor: a config that never imports the adapters at all would pass
        the assertion above by being broken."""
        from iriguchi.config import IriguchiConfig

        config = IriguchiConfig(local=True, local_url="http://127.0.0.1:1/v1", local_model="m")
        assert config.local_answerer().name.startswith("m at ")

    def test_config_no_longer_exposes_the_adapter_names(self) -> None:
        """Two tests were monkeypatching `iriguchi.config.MamoriChannel`. That
        name is gone from the module on purpose, and anything patching it now
        gets an `AttributeError` rather than a silently ineffective patch."""
        import iriguchi.config as config

        assert not hasattr(config, "OpenAICompatibleModel")
        assert not hasattr(config, "MamoriChannel")


class TestFindingsFromSomebodyElsesAnalyzer:
    """R5. `mamori inspect --json` -> `iriguchi route --findings -`, no import."""

    RESULTS = json.dumps([{"entity_type": "PERSON", "start": 0, "end": 5, "score": 0.9}])

    def test_from_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "f.json"
        path.write_text(self.RESULTS, encoding="utf-8")
        code, out = _run(["route", "--json", "--findings", str(path), "Alice, prove the lemma."])
        assert code == EXIT_OK
        document = _doc(out)
        assert [f["rule"] for f in document["sensitivity"]["findings"]] == ["presidio.person"]
        assert [r["destination"] for r in document["removed"]] == ["external"]

    def test_from_standard_input_with_the_prompt_in_argv(self) -> None:
        code, out = _run(
            ["route", "--json", "--findings", "-", "Alice, prove the lemma."],
            self.RESULTS.encode("utf-8"),
        )
        assert code == EXIT_OK
        assert [f["source"] for f in _doc(out)["sensitivity"]["findings"]] == ["presidio"]

    def test_both_on_standard_input_is_refused(self) -> None:
        """One stream cannot carry two documents."""
        code, out = _run(["route", "--findings", "-", "-"], self.RESULTS.encode("utf-8"))
        assert code == EXIT_ERROR
        assert "both read standard input" in out

    def test_with_a_named_scanner_is_refused(self, tmp_path: Path) -> None:
        """Two intentions. The same rule the library's `route()` applies."""
        path = tmp_path / "f.json"
        path.write_text(self.RESULTS, encoding="utf-8")
        code, out = _run(["--scanner", "fallback", "route", "--findings", str(path), "hi"])
        assert code == EXIT_ERROR
        assert "Pick the one you meant" in out

    def test_an_empty_array_means_nothing_found_not_scan(self, tmp_path: Path) -> None:
        """`[]` and *no `--findings`* are different answers. The fallback would
        have caught this address; the caller said their analyzer already
        looked, and a second opinion nobody asked for is not a favour."""
        path = tmp_path / "none.json"
        path.write_text("[]", encoding="utf-8")
        code, out = _run(["route", "--json", "--findings", str(path), "Email tanaka@example.com"])
        assert code == EXIT_OK
        assert _doc(out)["sensitivity"]["findings"] == []

    def test_something_that_is_not_an_array_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "f.json"
        path.write_text('{"results": []}', encoding="utf-8")
        code, out = _run(["route", "--findings", str(path), "hi"])
        assert code == EXIT_ERROR
        assert "JSON array" in out

    def test_a_malformed_result_names_its_index(self, tmp_path: Path) -> None:
        path = tmp_path / "f.json"
        path.write_text('[{"entity_type": "PERSON", "start": 0}]', encoding="utf-8")
        code, out = _run(["route", "--findings", str(path), "hi"])
        assert code == EXIT_ERROR
        assert "result 0" in out


class TestBatch:
    """U4. Five cards, one interpreter start."""

    LINES: ClassVar[list[dict[str, Any]]] = [
        {"id": "a", "prompt": "Summarise this article in three lines."},
        {"id": 7, "prompt": "Email tanaka@example.com the figures."},
        {
            "id": "c",
            "prompt": "Alice, prove the lemma.",
            "findings": [{"entity_type": "PERSON", "start": 0, "end": 5, "score": 0.9}],
        },
    ]

    @staticmethod
    def _jsonl(rows: list[dict[str, Any]]) -> bytes:
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode("utf-8")

    def test_one_line_per_prompt_in_order_with_ids_echoed(self) -> None:
        code, out = _run(["route", "--batch"], self._jsonl(self.LINES))
        assert code == EXIT_OK
        rows = [json.loads(line) for line in out.splitlines() if line.strip()]
        assert [r["id"] for r in rows] == ["a", 7, "c"]
        assert all(r["contract"] == "iriguchi.route-batch/1-draft" for r in rows)
        assert all(r["decision"]["contract"] == "iriguchi.routing-decision/1" for r in rows)

    def test_the_frozen_document_is_inside_untouched(self) -> None:
        """The envelope carries the `id`; `routing-decision/1` cannot grow one
        and does not."""
        _, out = _run(["route", "--batch"], self._jsonl(self.LINES))
        first = json.loads(out.splitlines()[0])["decision"]
        assert "id" not in first

    def test_per_line_findings_are_honoured(self) -> None:
        _, out = _run(["route", "--batch"], self._jsonl(self.LINES))
        third = json.loads(out.splitlines()[2])["decision"]
        assert [f["rule"] for f in third["sensitivity"]["findings"]] == ["presidio.person"]

    def test_a_malformed_line_fails_the_whole_batch_with_nothing_written(self) -> None:
        """A consumer holding three decisions and a crash cannot tell them from a
        complete run. Validated first, written after."""
        code, out = _run(["route", "--batch"], b'{"id":1,"prompt":"ok"}\nnot json\n')
        assert code == EXIT_ERROR
        assert "batch line 2 is not JSON" in out
        assert "route-batch" not in out

    def test_an_unknown_key_is_refused_not_ignored(self) -> None:
        """A misspelled `findings` would silently run a scan the caller thought
        they had replaced."""
        code, out = _run(["route", "--batch"], b'{"prompt":"ok","finding":[]}\n')
        assert code == EXIT_ERROR
        assert "finding" in out and "nobody reads" in out

    def test_exit_two_when_any_line_was_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The strictest line wins, so a script can still tell "all decided"
        from "some refused" with one number."""
        monkeypatch.delenv("IRIGUCHI_EXTERNAL")
        monkeypatch.delenv("IRIGUCHI_LOCAL")
        code, out = _run(["route", "--batch"], self._jsonl(self.LINES))
        assert code == EXIT_REFUSED
        rows = [json.loads(line) for line in out.splitlines()]
        assert all(r["decision"]["route"] == "refused" for r in rows)

    def test_blank_lines_are_skipped(self) -> None:
        code, out = _run(["route", "--batch"], b'\n{"prompt":"ok"}\n\n')
        assert code == EXIT_OK
        assert len(out.splitlines()) == 1

    def test_an_empty_batch_is_refused(self) -> None:
        code, out = _run(["route", "--batch"], b"\n\n")
        assert code == EXIT_ERROR
        assert "read no prompts" in out

    def test_a_prompt_argument_has_nowhere_to_go(self) -> None:
        code, out = _run(["route", "--batch", "hello"], b'{"prompt":"ok"}\n')
        assert code == EXIT_ERROR
        assert "nowhere to go" in out

    def test_top_level_findings_are_refused_in_batch(self, tmp_path: Path) -> None:
        path = tmp_path / "f.json"
        path.write_text("[]", encoding="utf-8")
        code, out = _run(["route", "--batch", "--findings", str(path)], b'{"prompt":"ok"}\n')
        assert code == EXIT_ERROR
        assert "on each line" in out

    def test_no_part_of_any_prompt_reaches_the_output(self) -> None:
        """ADR-0006 does not get a batch exemption."""
        _, out = _run(["route", "--batch"], self._jsonl(self.LINES))
        for word in ("Alice", "tanaka@example.com", "Summarise"):
            assert word not in out


class TestRouteWithoutAPromptOrABatch:
    def test_is_told_what_it_needs(self) -> None:
        code, out = _run(["route"])
        assert code == EXIT_ERROR
        assert "--batch" in out
