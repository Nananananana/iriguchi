"""The outbound path, against the real mamori.

Skipped when mamori is absent; **failed** when it is installed and broken. Same
gate as `test_mamori_scanner.py`, for the same reason.

Two things this file is arranged around.

`TestNothingIsSent` is first because it is the guarantee the whole project rests
on, and because this is the first module in iriguchi that could break it. The
suite runs with `socket.socket` poisoned, so every test here is already evidence;
that class says so where somebody looking for it would look.

`TestWhatItRefuses` is the longest, and each of its cases is a clause of
`mamori.protection-scope/1` that a consumer could meet halfway. Meeting a
contract halfway is the failure the contract was written to prevent.
"""

from __future__ import annotations

from typing import Any

import pytest

from iriguchi.errors import EscalationRefusedError, RestorationError
from iriguchi.infrastructure.channels.mamori_channel import (
    CONTRACT,
    MamoriChannel,
    MamoriEscalation,
)
from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state
from iriguchi.ports.channel import Escalation, EscalationChannel

_STATE, _DETAIL = mamori_state()

pytestmark = pytest.mark.skipif(
    _STATE is SiblingState.ABSENT, reason="mamori is not installed; the seam has one side"
)

SENSITIVE = "田中太郎さんへ tanaka@example.com から連絡がありました。"
HARMLESS = "この二つのアルゴリズムを比較してください。"
CREDENTIAL = "設定は api_key = sk-live-51H8xQeMwvJ4tRbN7cZpLdKf です"


def a_record(**overrides: Any) -> dict[str, Any]:
    """A well-formed record, for tests that bend exactly one clause."""
    return {
        "contract": CONTRACT,
        "by": "mamori/0.26.0",
        "scope": "session-000000000000",
        "reversible": True,
        "mode": "placeholder",
        "placeholders": [{"token": "<PERSON_001>", "kind": "PERSON"}],
        "protected": [],
        "masked": [],
    } | overrides


def test_mamori_is_installed_and_importable() -> None:
    """A broken sibling is a finding, not a skip."""
    assert _STATE is SiblingState.AVAILABLE, _DETAIL


class TestNothingIsSent:
    """The guarantee this module could have broken, and did not.

    Every test in this suite runs with `socket.socket` poisoned by
    `conftest.py`, so all of them are evidence. This is where somebody looking
    for the claim will look for it.
    """

    def test_preparing_an_escalation_opens_no_socket(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            assert escalation.protected_text

    def test_the_whole_round_trip_opens_no_socket(self) -> None:
        """Protection and restoration are both local. The only thing that would
        ever leave is the string in the middle, and handing it to somebody is a
        separate call this port does not have."""
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            assert escalation.restore("Re: " + escalation.protected_text)

    def test_the_channel_has_no_send_method(self) -> None:
        """`prepare` and sending are deliberately different operations, so that
        `route --dry-run` can walk this path without an outbound call existing
        on it."""
        assert not hasattr(MamoriChannel(), "send")
        assert not hasattr(MamoriChannel().prepare(HARMLESS), "send")


class TestTheRoundTrip:
    def test_the_protected_text_carries_no_values(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            assert "田中太郎" not in escalation.protected_text
            assert "tanaka@example.com" not in escalation.protected_text
            assert "<PERSON_001>" in escalation.protected_text

    def test_an_answer_comes_back_whole(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            answer = escalation.restore(f"I will reply to {escalation.protected_text}")
        assert "田中太郎" in answer
        assert "tanaka@example.com" in answer
        assert "<PERSON_001>" not in answer

    def test_a_prompt_with_nothing_in_it_passes_through(self) -> None:
        with MamoriChannel().prepare(HARMLESS) as escalation:
            assert escalation.protected_text == HARMLESS
            assert not escalation.findings

    def test_it_satisfies_the_ports(self) -> None:
        channel = MamoriChannel()
        assert isinstance(channel, EscalationChannel)
        with channel.prepare(HARMLESS) as escalation:
            assert isinstance(escalation, Escalation)


class TestItReportsWhatTheScannerMissed:
    """The one job reading the record does. ADR-0013.

    This path is only reached when the routing decision said `CLEAR`, so
    anything mamori protected is something iriguchi's scanner did not find.
    """

    def test_a_disagreement_becomes_a_reason(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            rules = {finding.rule for finding in escalation.findings}
        assert "mamori-channel.protected-person" in rules
        assert "mamori-channel.protected-email" in rules

    def test_a_reason_says_the_scanner_missed_it(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            assert all("missed" in finding.detail for finding in escalation.findings)

    def test_agreement_is_silence(self) -> None:
        with MamoriChannel().prepare(HARMLESS) as escalation:
            assert escalation.findings == ()

    def test_the_findings_are_ordered(self) -> None:
        first = MamoriChannel().prepare(SENSITIVE)
        second = MamoriChannel().prepare(SENSITIVE)
        try:
            assert [f.rule for f in first.findings] == [f.rule for f in second.findings]
        finally:
            first.close()
            second.close()


class TestWhatTheRecordDoesNotCarryOut:
    """Placeholder tokens, the scope and the policy hash are read and dropped.

    ADR-0013: the record is read and none of it is kept. A token is derivable
    from the protected text, so it is not a new disclosure to somebody holding
    that -- and a `Reason` goes places the protected text does not.
    """

    def test_no_token_reaches_a_finding(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            rendered = repr(escalation.findings)
        assert "<PERSON_001>" not in rendered
        assert "<EMAIL_001>" not in rendered

    def test_no_scope_or_policy_hash_reaches_a_finding(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            rendered = repr(escalation.findings)
        assert "session-" not in rendered
        assert "sha256:" not in rendered

    def test_no_value_reaches_a_finding(self) -> None:
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            rendered = repr(escalation.findings)
        assert "田中太郎" not in rendered
        assert "tanaka@example.com" not in rendered

    def test_the_escalation_keeps_no_record(self) -> None:
        """Not stored under another name either."""
        with MamoriChannel().prepare(SENSITIVE) as escalation:
            held = repr(vars(escalation))
        assert CONTRACT not in held
        assert "policy_hash" not in held


class TestWhatItRefuses:
    """Each case is a clause of the contract a consumer could meet halfway."""

    def test_a_credential_is_the_last_gate(self) -> None:
        """mamori blocks rather than protecting one. Reaching here means a
        scanner already missed it, and going round the last gate would send the
        thing two layers exist to stop."""
        with pytest.raises(EscalationRefusedError, match="credential reached the outbound path"):
            MamoriChannel().prepare(CREDENTIAL)

    def test_an_unrecognised_contract(self) -> None:
        channel = MamoriChannel()
        with pytest.raises(EscalationRefusedError, match="declares contract"):
            channel._read(a_record(contract="mamori.protection-scope/2"))

    @pytest.mark.parametrize("mode", ["surrogate", "mixed"])
    def test_a_mode_this_build_cannot_read(self, mode: str) -> None:
        """The schema's own words: a consumer that understands only
        `placeholder` must refuse these rather than read `placeholders` and
        conclude the document is fully enumerated."""
        channel = MamoriChannel()
        with pytest.raises(EscalationRefusedError, match="fully enumerated"):
            channel._read(a_record(mode=mode))

    def test_a_protection_that_cannot_be_undone(self) -> None:
        channel = MamoriChannel()
        with pytest.raises(EscalationRefusedError, match="not reversible"):
            channel._read(a_record(reversible=False))

    def test_an_absent_reversible_reads_as_false(self) -> None:
        """A wrong `true` fails silently, so absence takes the safe reading."""
        channel = MamoriChannel()
        record = a_record()
        del record["reversible"]
        with pytest.raises(EscalationRefusedError, match="not reversible"):
            channel._read(record)

    def test_none_of_these_is_a_degradation(self) -> None:
        """Every refusal leaves the prompt where it was. There is no path that
        sends something less protected instead."""
        channel = MamoriChannel()
        for record in (
            a_record(contract="other/1"),
            a_record(mode="surrogate"),
            a_record(reversible=False),
        ):
            with pytest.raises(EscalationRefusedError):
                channel._read(record)


class TestRestoration:
    def test_a_partly_restorable_answer_is_refused(self) -> None:
        """A token the mapping does not know is a fact-shaped hole. Returning
        the rest would read as complete."""
        with (
            MamoriChannel().prepare(SENSITIVE) as escalation,
            pytest.raises(RestorationError, match="resolve to nothing"),
        ):
            escalation.restore("See <PERSON_042> about it")

    def test_restoring_after_close_is_refused(self) -> None:
        escalation = MamoriChannel().prepare(SENSITIVE)
        protected = escalation.protected_text
        escalation.close()
        with pytest.raises(RestorationError, match="closed"):
            escalation.restore(protected)

    def test_closing_twice_is_harmless(self) -> None:
        """A caller in a `finally` should not have to know whether it ran."""
        escalation = MamoriChannel().prepare(HARMLESS)
        escalation.close()
        escalation.close()


class TestTheChannelNeedsMamori:
    def test_it_refuses_to_exist_without_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not a downgrade to sending unprotected. There is no such path."""
        monkeypatch.setattr(
            "iriguchi.infrastructure.channels.mamori_channel.mamori_state",
            lambda: (SiblingState.ABSENT, ""),
        )
        with pytest.raises(EscalationRefusedError, match="will not send one unprotected"):
            MamoriChannel()

    def test_a_broken_install_is_not_reported_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "iriguchi.infrastructure.channels.mamori_channel.mamori_state",
            lambda: (SiblingState.BROKEN, "ImportError: locale"),
        )
        with pytest.raises(EscalationRefusedError, match="cannot be imported"):
            MamoriChannel()


class TestTheMappingHasALifetime:
    def test_closing_releases_the_session(self) -> None:
        """The mapping is the highest-value object in the round trip and exists
        for exactly as long as the round trip."""
        escalation = MamoriChannel().prepare(SENSITIVE)
        closed: list[bool] = []

        class Watched:
            def close(self) -> None:
                closed.append(True)

            def restore(self, text: str) -> Any:  # pragma: no cover -- not reached
                raise AssertionError

        escalation._session = Watched()
        escalation.close()
        assert closed == [True]

    def test_the_context_manager_closes_it(self) -> None:
        escalation = MamoriEscalation(_Recording(), "text", ())
        with escalation:
            pass
        assert escalation._session.closed


class _Recording:
    closed = False

    def close(self) -> None:
        self.closed = True

    def restore(self, text: str) -> Any:  # pragma: no cover -- not reached
        raise AssertionError


class TestThroughTheCli:
    """`route --explain` on an outbound route shows what would arrive.

    The first thing `--dry-run` has had that is worth looking at. Everything
    below runs with the network poisoned, so "shows what would leave without
    sending it" is a property of the run and not a claim about it.
    """

    def run_cli(self, *argv: str) -> str:
        import io

        from iriguchi.interfaces.cli.main import main

        out = io.StringIO()
        main(list(argv), out=out)
        return out.getvalue()

    def test_an_outbound_route_shows_the_protected_text(self) -> None:
        output = self.run_cli("--local", "--external", "route", "--explain", "--dry-run", HARMLESS)
        assert "would leave" in output
        assert HARMLESS in output

    def test_a_local_route_shows_nothing_of_the_kind(self) -> None:
        """There is nothing to protect for a prompt that is not going out, and
        preparing one anyway would create a mapping to answer a question nobody
        asked."""
        output = self.run_cli("--local", "--external", "route", "--explain", "--dry-run", SENSITIVE)
        assert "route        LOCAL" in output
        assert "would leave" not in output

    def test_the_seam_reports_what_the_fallback_missed(self) -> None:
        """The demonstration this whole seam exists for.

        The built-in scanner cannot find a name without an honorific -- its own
        largest documented gap -- so it clears this prompt and the router sends
        it. mamori then protects the name on the way out, and the person is told
        that the decision was made on less than the whole picture.
        """
        prompt = "田中と二つのアルゴリズムを比較して、計算量を証明してください。"
        output = self.run_cli("--local", "--external", "route", "--explain", "--dry-run", prompt)

        assert "route        EXTERNAL" in output
        assert "<PERSON_001>" in output, "the name should have been replaced"
        assert "田中と二つ" not in output.split("would leave")[1], "the name still left"
        assert "the scanner that cleared this prompt missed them" in output

    def test_choosing_mamori_as_the_scanner_closes_that_gap(self) -> None:
        """The contrast. With mamori scanning, the same prompt never leaves, so
        there is nothing for the channel to catch."""
        prompt = "田中と二つのアルゴリズムを比較して、計算量を証明してください。"
        output = self.run_cli(
            "--local", "--external", "--scanner", "mamori", "route", "--explain", prompt
        )
        assert "route        LOCAL" in output
        assert "would leave" not in output

    def test_it_still_says_it_sent_nothing(self) -> None:
        output = self.run_cli("--local", "--external", "route", "--explain", "--dry-run", HARMLESS)
        assert "sent         nothing" in output


class TestWhenMamoriBreaksMidFlight:
    """The broad excepts. Each converts an unexpected failure into a refusal
    with the session closed, because a channel that leaks a session on the way
    out leaks a mapping, and one that raises something other than
    `EscalationRefusedError` invites a caller to treat it as a bug rather than as a
    reason not to send."""

    def test_a_protection_that_explodes_refuses_and_closes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[bool] = []

        class Exploding:
            def protect(self, text: str) -> Any:
                raise RuntimeError("the rule table did not load")

            def close(self) -> None:
                closed.append(True)

        monkeypatch.setattr("mamori.PrivacySession", lambda **kw: Exploding())
        with pytest.raises(EscalationRefusedError, match="could not protect"):
            MamoriChannel().prepare(HARMLESS)
        assert closed == [True], "the session was left open"

    def test_an_unreadable_record_refuses_and_closes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        channel = MamoriChannel()

        def explode(*args: object, **kwargs: object) -> None:
            raise ValueError("not a record")

        monkeypatch.setattr(
            "iriguchi.infrastructure.channels.mamori_channel.protection_record",
            explode,
            raising=False,
        )
        monkeypatch.setattr("mamori.provenance.protection_record", explode)
        with pytest.raises(EscalationRefusedError, match="could not be read"):
            channel.prepare(HARMLESS)

    def test_a_refused_record_closes_the_session_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The `except EscalationRefusedError: close; raise` arm. A refusal is still
        an exit, and an exit still has to release the mapping."""
        monkeypatch.setattr(
            "mamori.provenance.protection_record",
            lambda *a, **k: a_record(mode="surrogate"),
        )
        with pytest.raises(EscalationRefusedError, match="fully enumerated"):
            MamoriChannel().prepare(HARMLESS)

    def test_a_restoration_that_explodes_is_a_restoration_error(self) -> None:
        class Exploding:
            def restore(self, text: str) -> Any:
                raise RuntimeError("the mapping store is gone")

            def close(self) -> None:
                pass

        escalation = MamoriEscalation(Exploding(), "text", ())
        with pytest.raises(RestorationError, match="could not restore"):
            escalation.restore("anything")


class TestTheCliWithoutMamori:
    def test_it_says_it_cannot_say(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An outbound route with no protector available. The route stands and
        the preview cannot be produced, and saying which is the point."""
        import io

        from iriguchi.interfaces.cli.main import main

        monkeypatch.setattr(
            "iriguchi.config.MamoriChannel",
            lambda *a, **k: (_ for _ in ()).throw(
                EscalationRefusedError("mamori is not installed")
            ),
        )
        out = io.StringIO()
        main(["--local", "--external", "route", "--explain", "--dry-run", HARMLESS], out=out)
        assert "cannot say" in out.getvalue()

    def test_a_refused_escalation_says_nothing_was_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import io

        from iriguchi.interfaces.cli.main import main

        class Refusing:
            def prepare(self, prompt: str) -> Any:
                raise EscalationRefusedError("a credential reached the outbound path")

        monkeypatch.setattr("iriguchi.config.MamoriChannel", lambda *a, **k: Refusing())
        out = io.StringIO()
        main(["--local", "--external", "route", "--explain", "--dry-run", HARMLESS], out=out)
        assert "would leave    nothing" in out.getvalue()
