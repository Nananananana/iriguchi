"""The console the owner actually has.

A default Japanese Windows terminal is `cp932`, and `cp932` has no `é`, no em
dash and no bullet. akashi found every one of their printing commands crashing
on one, and named why it survived construction:

    Every command run while building was prefixed with `PYTHONUTF8=1` --
    exactly the setting the reader does not have. CI could not catch it either:
    a runner's locale is UTF-8, and more runners of the same kind do not make a
    machine capable of this failure.

**A scan of this repository's string literals reports zero hits and is right,
and it could never have found iriguchi's version of this.** The characters come
from the prompt. `ask --dry-run` echoes the protected text and `ask` echoes the
model's answer, and both crashed on `é`.

So the test builds the console rather than looking for characters: a real
`TextIOWrapper` over bytes, `cp932`, `errors="strict"` — which is what a
terminal is. It runs on Linux and on a UTF-8 machine, because the encoding is
constructed rather than inherited. That is the whole point: **the failure has to
be producible somewhere, and no number of UTF-8 runners produces it.**

Two things this suite has to keep apart, and they are the same distinction the
project keeps making elsewhere:

- **the chrome** — rule ids, band names, spans — must simply encode. It is
  ASCII by construction because *messages carry rule ids, spans and types,
  never a matched value*, and that privacy rule is why `route --explain` cannot
  hit this bug at all.
- **the content** — the answer, the protected text — cannot be constrained, so
  it is replaced *and announced*. A silent `?` would make the display disagree
  with the payload, in the one command whose purpose is letting somebody check
  before anything leaves.
"""

from __future__ import annotations

import io

import pytest

from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state
from iriguchi.interfaces.cli import main as cli
from iriguchi.interfaces.cli.console import print_content

_STATE, _DETAIL = mamori_state()

#: One character from each family cp932 lacks, and one it has. Verified against
#: the codec rather than assumed: `…`, `→` and `“` are all **present** in cp932,
#: which is why a hand-written list of "typographic characters" is not the same
#: list as this one.
ABSENT = {"em dash": "—", "e acute": "é", "bullet": "•"}
PRESENT = {"ellipsis": "…", "arrow": "→", "hiragana": "あ"}


def console() -> tuple[io.BytesIO, io.TextIOWrapper]:
    """What a terminal is: bytes, an encoding, and no forgiveness."""
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(raw, encoding="cp932", errors="strict", newline="")


def read(raw: io.BytesIO, stream: io.TextIOWrapper) -> str:
    stream.flush()
    return raw.getvalue().decode("cp932")


class TestTheCodecItself:
    """Because a list of characters somebody believed cp932 lacked is not a
    list of characters cp932 lacks."""

    @pytest.mark.parametrize("character", ABSENT.values(), ids=list(ABSENT))
    def test_the_absent_ones_really_are(self, character: str) -> None:
        with pytest.raises(UnicodeEncodeError):
            character.encode("cp932")

    @pytest.mark.parametrize("character", PRESENT.values(), ids=list(PRESENT))
    def test_the_present_ones_really_are(self, character: str) -> None:
        """`…` is in cp932. A report that flags an ellipsis as a cp932 hazard
        is a false positive, and one was passed around today."""
        assert character.encode("cp932")


class TestPrintContent:
    def test_text_the_console_can_draw_goes_through_unchanged(self) -> None:
        raw, stream = console()
        print_content("田中さんへ →…", stream)
        assert read(raw, stream).strip() == "田中さんへ →…"

    @pytest.mark.parametrize("character", ABSENT.values(), ids=list(ABSENT))
    def test_a_character_it_cannot_draw_does_not_raise(self, character: str) -> None:
        raw, stream = console()
        print_content(f"before {character} after", stream)
        assert "before" in read(raw, stream)

    def test_the_substitution_is_announced_and_counted(self) -> None:
        """A silent `?` is worse than the crash. It makes the display disagree
        with the payload, in the command that exists for checking the payload."""
        raw, stream = console()
        print_content("a — b é c — d", stream)
        printed = read(raw, stream)
        assert "2 character(s)" in printed, "distinct characters, not occurrences"
        assert "U+2014" in printed and "U+00E9" in printed
        assert "unchanged" in printed

    def test_nothing_is_announced_when_nothing_was_replaced(self) -> None:
        """A warning that always fires is a banner."""
        raw, stream = console()
        print_content("ordinary text", stream)
        assert "cannot show" not in read(raw, stream)

    def test_a_stream_with_no_encoding_is_treated_as_utf8(self) -> None:
        """`io.StringIO` has none. Assuming UTF-8 there is what Python does,
        and it keeps a test from believing it simulated a console."""
        out = io.StringIO()
        print_content("— é", out)
        assert "cannot show" not in out.getvalue()

    def test_the_indent_is_applied_to_every_line(self) -> None:
        raw, stream = console()
        print_content("one\ntwo", stream, indent="    ")
        assert read(raw, stream).splitlines() == ["    one", "    two"]


class TestEveryCommandSurvivesTheConsole:
    """The chrome, which must encode without help."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["route", "田中太郎さんに tanaka@example.com で連絡"],
            ["route", "--explain", "Refactor this and explain why, step by step."],
            ["config"],
            ["doctor"],
            ["demo"],
            ["eval"],
        ],
        ids=["route", "route --explain", "config", "doctor", "demo", "eval"],
    )
    def test_it_prints_without_a_unicode_error(
        self, argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        for key in ("IRIGUCHI_LOCAL", "IRIGUCHI_EXTERNAL"):
            monkeypatch.delenv(key, raising=False)
        raw, stream = console()
        cli.main(argv, stream)
        assert read(raw, stream), "the command printed nothing, so nothing was tested"

    @pytest.mark.parametrize("character", ABSENT.values(), ids=list(ABSENT))
    def test_a_prompt_the_console_cannot_draw_does_not_kill_route(
        self, character: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`route` survives this for a reason worth knowing: it never prints
        the prompt. The security rule that keeps values out of messages keeps
        the encoding hazard out too."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        raw, stream = console()
        cli.main(["route", "--explain", f"Fix this {character} thing"], stream)
        assert "route" in read(raw, stream)


@pytest.mark.skipif(
    _STATE is not SiblingState.AVAILABLE,
    reason=f"the outbound path needs mamori ({_DETAIL or 'absent'})",
)
class TestTheTwoPlacesThatEchoContent:
    """`ask --dry-run` and `ask` are the only commands that print what the
    person typed or what a model said. Both crashed."""

    @pytest.mark.parametrize("character", ABSENT.values(), ids=list(ABSENT))
    def test_dry_run_shows_what_would_leave_instead_of_dying(
        self, character: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL_URL", "https://api.example.invalid/v1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL_MODEL", "a-model")
        raw, stream = console()
        code = cli.main(
            [
                "ask",
                "--dry-run",
                f"Refactor this {character} and explain why, step by step, with alternatives",
            ],
            stream,
        )
        printed = read(raw, stream)
        assert code == cli.EXIT_OK
        # Show the protection ran before believing anything about the output.
        assert "would leave" in printed and "cannot say" not in printed, (
            "the escalation did not run, so the line under test never executed"
        )
        assert "cannot show" in printed
