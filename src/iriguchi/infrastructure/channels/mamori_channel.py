"""mamori as the escalation channel. The path `ESCALATED` was promising.

Until this existed, `ESCALATED` was a verdict with nothing behind it: iriguchi
decided a prompt could leave and had no way to protect it on the way out, which
is moving a problem rather than solving one.

**Nothing here sends.** `prepare` protects and returns; sending is somebody
else's call, made after a person has had the chance to look at what would go.
That is what keeps `route --dry-run` honest now that an outbound path exists at
all.

Three behaviours are worth reading before changing anything.

**The record is read and never kept** (ADR-0013). It carries placeholder tokens,
a scope and a policy hash; what comes out of this module is a kind, a count and
the name of the scanner that missed it. Reading it does one job nothing else
does: iriguchi only escalates when its own scanner said `CLEAR`, so anything
mamori protected is something iriguchi's scanner missed, and the person is the
only one who can act on that.

**Every disagreement with the contract is a refusal**, never a partial read --
and that means every obligation, not the ones this module found convenient.
Required keys, the closed key set, the placeholder entry shape. A consumer as
loose as this one was is a consumer claiming a strictness it does not have.

**The contract identifier is the field that carries the state, and it is read
first.** A record holding surrogates declares `.../1+surrogate` and is refused
by the check already here. This module used to say `mode` was that mechanism,
quoting a version of the schema that has since moved the rule -- and which now
says plainly that `mode` is *not* a switch selecting which array to read.

**mamori's own block is the last gate.** It refuses to protect a credential at
all (its ADR-0002). A credential reaching here means a scanner already missed
one, and the answer to the last gate closing is not to go round it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...domain.reason import Reason
from ...errors import EscalationRefusedError, RestorationError
from ..scanners.mamori_scanner import SiblingState, mamori_state

__all__ = ["MamoriChannel", "MamoriEscalation"]

_SOURCE = "mamori-channel"

#: The one contract this build knows how to read. An unrecognised one is
#: refused rather than parsed for the fields it happens to recognise -- the
#: schema says so, and it is the same rule iriguchi applies to its own settings.
#:
#: **This is the field that carries the state**, and reading it first is the
#: whole mechanism. A record holding any surrogate declares
#: `mamori.protection-scope/1+surrogate`, so a token-only consumer refuses it
#: through the check it already has rather than through a rule it has to
#: remember every time. `mode` used to be where that lived; the schema moved it
#: here and now says outright that `mode` is *not* a switch selecting which
#: array to read.
CONTRACT = "mamori.protection-scope/1"

#: Every key the schema requires. Missing one means the document is not a record
#: of this contract, whatever its `contract` field says.
REQUIRED = frozenset(
    {"contract", "by", "scope", "reversible", "mode", "placeholders", "protected", "masked"}
)

#: Every key the schema permits. It sets `additionalProperties: false`, so a key
#: outside this set is not a newer producer being helpful -- it is a document
#: this build cannot claim to have understood.
PERMITTED = REQUIRED | {"recall", "policy_hash"}

#: What one entry of `placeholders` must be, exactly.
PLACEHOLDER_KEYS = frozenset({"token", "kind"})

#: The substitution mode iriguchi understands. Kept as a check and **not** as
#: the mechanism: the contract identifier above is what stops a half-read. This
#: is a consistency check on a summary field, which is a far smaller claim than
#: the one this constant used to carry.
UNDERSTOOD_MODE = "placeholder"


class MamoriEscalation:
    """One protected prompt, and the session that can put it back."""

    def __init__(self, session: Any, protected_text: str, findings: Sequence[Reason]) -> None:
        self._session = session
        self._protected_text = protected_text
        self._findings = tuple(findings)
        self._closed = False

    @property
    def protected_text(self) -> str:
        return self._protected_text

    @property
    def findings(self) -> Sequence[Reason]:
        return self._findings

    def restore(self, response: str) -> str:
        """Put the real values back.

        Refuses a partial restoration. mamori reports placeholders it could not
        resolve; an answer containing one of those has a token where a fact
        should be, and returning it would let a `<PERSON_001>` be read as
        something the model said.
        """
        if self._closed:
            raise RestorationError("this escalation has been closed; its mapping is gone")
        try:
            result = self._session.restore(response)
        except Exception as failure:
            raise RestorationError(
                f"mamori could not restore the answer: {type(failure).__name__}: {failure}"
            ) from failure

        unknown = getattr(result, "unknown", ()) or ()
        if unknown:
            raise RestorationError(
                f"{len(unknown)} placeholder(s) in the answer resolve to nothing. A "
                "partly restored answer reads as complete and quotes a placeholder as "
                "though it were a fact."
            )
        return str(result.text)

    def close(self) -> None:
        """Release the mapping. Idempotent, because a caller in a `finally`
        should not have to know whether it already ran."""
        if not self._closed:
            self._closed = True
            self._session.close()

    def __enter__(self) -> MamoriEscalation:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class MamoriChannel:
    """Protects an outbound prompt through mamori. Sends nothing."""

    name = "mamori"

    def __init__(self, locales: Sequence[str] = ("ja", "en")) -> None:
        state, detail = mamori_state()
        if state is SiblingState.ABSENT:
            raise EscalationRefusedError(
                "mamori is not installed, so there is nothing to protect an outbound "
                "prompt with. iriguchi will not send one unprotected: install mamori "
                "from a checkout (`uv pip install -e ../mamori`), or use the local "
                "route only."
            )
        if state is SiblingState.BROKEN:
            raise EscalationRefusedError(
                f"mamori is installed and cannot be imported ({detail}). That is not "
                "the same as it being absent, and it is not a reason to send anything."
            )
        self._locales = tuple(locales)

    def prepare(self, prompt: str) -> MamoriEscalation:
        """Protect `prompt`. Return what would leave. Send nothing."""
        from mamori import PrivacySession
        from mamori.errors import PolicyViolationError
        from mamori.provenance import protection_record

        session = PrivacySession(locales=list(self._locales))
        try:
            result = session.protect(prompt)
        except PolicyViolationError as blocked:
            session.close()
            # The last gate. mamori blocks a credential rather than protecting
            # it, so reaching this means a scanner already missed one -- and
            # going round it would send the thing two layers were built to stop.
            raise EscalationRefusedError(
                f"mamori refused to protect this prompt: {blocked}. A credential "
                "reached the outbound path, which means the scanner missed it. "
                "Nothing was sent."
            ) from blocked
        except Exception as failure:
            session.close()
            raise EscalationRefusedError(
                f"mamori could not protect this prompt: {type(failure).__name__}: {failure}"
            ) from failure

        try:
            record = protection_record(result, session=session)
            findings = self._read(record)
        except EscalationRefusedError:
            session.close()
            raise
        except Exception as failure:
            session.close()
            raise EscalationRefusedError(
                f"the protection record could not be read: {type(failure).__name__}: {failure}"
            ) from failure

        return MamoriEscalation(session, result.protected_text, findings)

    def _read(self, record: dict[str, Any]) -> list[Reason]:
        """Check the record against every obligation, then throw it away.

        Nothing from the record survives this method except kinds and counts.
        Tokens, scope and `policy_hash` are read to make decisions and are not
        carried out (ADR-0013).
        """
        contract = record.get("contract")
        if contract != CONTRACT:
            raise EscalationRefusedError(
                f"the protection record declares contract {contract!r}; this build "
                f"reads {CONTRACT!r}. Refusing rather than reading the fields it "
                "happens to recognise."
            )

        missing = REQUIRED - set(record)
        if missing:
            raise EscalationRefusedError(
                f"the protection record is missing {sorted(missing)}, which the "
                f"published schema requires. A document short of a required field is "
                "not a record of this contract, whatever its `contract` says."
            )

        unknown = set(record) - PERMITTED
        if unknown:
            raise EscalationRefusedError(
                f"the protection record carries {sorted(unknown)}, which the published "
                f"schema does not permit -- it sets `additionalProperties: false`. An "
                "unexpected key is not a newer producer being helpful; it is a document "
                "this build cannot claim to have understood."
            )

        # The one the contract identifier is *for*. A record declaring the plain
        # contract while carrying surrogates is the half-read the whole
        # mechanism exists to stop: `placeholders` would enumerate part of what
        # was protected, and reading it as all of it is the quiet failure. The
        # schema states it as an `if`/`then`; iriguchi runs no validator, so it
        # states it here.
        surrogates = record.get("protected") or ()
        if surrogates:
            raise EscalationRefusedError(
                f"the record declares {CONTRACT!r} and lists {len(surrogates)} "
                "surrogate-protected value(s). The schema forbids that combination, "
                "and the reason is the mistake this consumer would otherwise make: "
                "`placeholders` would enumerate part of what was protected, and "
                "reading it as the whole would be believing a half record."
            )

        for entry in record.get("placeholders", ()):
            keys = set(entry)
            if keys != PLACEHOLDER_KEYS:
                raise EscalationRefusedError(
                    f"a `placeholders` entry has keys {sorted(keys)}; the schema "
                    f"requires exactly {sorted(PLACEHOLDER_KEYS)}. A missing `kind` "
                    "would be counted as UNKNOWN, and an extra field could hold a "
                    "value, which this record is defined to carry none of."
                )

        mode = record.get("mode")
        if mode != UNDERSTOOD_MODE:
            raise EscalationRefusedError(
                f"the protection used mode {mode!r}. iriguchi understands "
                f"{UNDERSTOOD_MODE!r} only, and the contract requires a consumer that "
                "does to refuse the others rather than read `placeholders` and "
                "conclude the document is fully enumerated."
            )

        # Absent reads as false. A wrong `true` fails silently, which is the
        # direction the contract's own note picks against.
        if not record.get("reversible", False):
            raise EscalationRefusedError(
                "the protection is not reversible, so an answer could not be fully "
                "restored. iriguchi promised a round trip; half of one is worse than "
                "none, because it reads as complete."
            )

        return self._disagreements(record)

    def _disagreements(self, record: dict[str, Any]) -> list[Reason]:
        """What mamori protected that iriguchi's scanner had not found.

        This path is only reached when the routing decision said `CLEAR`, so
        every entry here is a miss. Kinds and counts; never a token.
        """
        kinds: dict[str, int] = {}
        for entry in record.get("placeholders", ()):
            kind = str(entry.get("kind", "UNKNOWN"))
            kinds[kind] = kinds.get(kind, 0) + 1

        return [
            Reason(
                rule=f"mamori-channel.protected-{kind.lower().replace('_', '-')}",
                source=_SOURCE,
                span=None,
                detail=(
                    f"mamori protected {count} {kind} value(s) on the way out, which "
                    f"the routing decision did not know about -- the scanner that "
                    f"cleared this prompt missed them. It leaves safely, with "
                    f"placeholders, and the decision was made on less than the whole "
                    f"picture."
                ),
            )
            for kind, count in sorted(kinds.items())
        ]
