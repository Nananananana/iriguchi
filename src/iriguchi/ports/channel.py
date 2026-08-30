"""What an escalation channel has to be.

The third port, and the first one that is allowed to send anything. Every other
port in this package proposes; this one acts — which is why the protocol is
shaped so that acting happens in two steps with the person's decision in
between.

`prepare` protects a prompt and returns what *would* leave. Nothing has gone
anywhere at that point, and `iriguchi route --explain --dry-run` stops there:
the promise that the deciding path cannot send survives because preparation and
sending are different methods.

`Escalation.restore` is the way back. It exists on the object rather than on the
channel because restoration needs the state that protection created -- mamori
holds the mapping in the session that protected the text, and a channel-level
`restore(text)` would have to guess which one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..domain.reason import Reason

__all__ = ["Escalation", "EscalationChannel"]


@runtime_checkable
class Escalation(Protocol):
    """One prompt, protected, and not yet sent."""

    @property
    def protected_text(self) -> str:
        """What would actually leave this machine.

        Safe to show a person -- that is most of what it is for. It is the
        answer to "what does the other end see", which nothing in v0.1 could
        answer, and it is the difference between a promise about protection and
        a look at it.
        """
        ...

    @property
    def findings(self) -> Sequence[Reason]:
        """What the protection noticed that the routing decision did not.

        Not a copy of the protection record. A record carries placeholder
        tokens, a scope and a policy hash; these carry a kind, a count and the
        name of the scanner that missed it, which is what a person can act on
        (ADR-0013).

        Empty is the ordinary case and means the two agreed.
        """
        ...

    def restore(self, response: str) -> str:
        """Put the real values back into an answer.

        Raises:
            RestorationError: if the answer cannot be fully restored. A partly
                restored answer is worse than none: it reads as complete and
                quotes a placeholder as though it were a fact.
        """
        ...

    def close(self) -> None:
        """Release the mapping.

        Not optional and not deferred to garbage collection. The mapping is the
        highest-value object in this round trip and it exists for exactly as
        long as the round trip does.
        """
        ...


@runtime_checkable
class EscalationChannel(Protocol):
    """Protects a prompt so that it can leave. Never sends it."""

    @property
    def name(self) -> str:
        """How this channel identifies itself in an explanation."""
        ...

    def prepare(self, prompt: str) -> Escalation:
        """Protect `prompt` and return what would be sent.

        Sends nothing. A channel that sent from here would put an outbound call
        inside the path `route --dry-run` walks, and the guarantee that a
        decision can be inspected without anything leaving would be gone.

        Raises:
            EscalationRefusedError: whenever the prompt must not leave after all --
                a protection that cannot be reversed, a record this build does
                not understand, or the protector's own refusal. Every one of
                these leaves the prompt where it is; none of them is a
                degradation to sending something less protected (ADR-0013).
        """
        ...
