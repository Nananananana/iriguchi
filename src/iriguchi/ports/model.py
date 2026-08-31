"""What answers a prompt.

The fourth port, and the second one allowed to touch a network. It is
deliberately the same shape for a model on this machine and a model on somebody
else's: **that difference is a hostname, not a code path.**

mamori reached this first and wrote down why, and the reasoning transfers
whole: a model here can be busy too -- weights loading, a queue draining -- so a
slow answer is slow wherever it came from. What distance changes is how long to
wait and what has to happen to the text first, and neither of those is a
different protocol.

So `ask` composes rather than branches:

    LOCAL      model.answer(prompt)
    ESCALATED  channel.prepare(prompt) -> model.answer(protected) -> restore
    REFUSED    nothing at all

The protection sits *between* the same two calls on one path and not on the
other, which is the whole difference between the destinations, visible in one
place. A second port for "the remote one" would have hidden it in a type.

**Nothing here decides anything.** By the time a `Model` is called the routing
decision is made and, on the outbound path, the protection is done. A model
that answers something unexpected is a weak model; it is not a route and it is
not a leak. kiseki put it best while shipping a producer that calls one: *the
answer is settled before it becomes a record.*
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["Model"]


@runtime_checkable
class Model(Protocol):
    """Text in, text out, over whatever wire the adapter owns."""

    @property
    def name(self) -> str:
        """How this model identifies itself in an explanation.

        Shown to a person before anything is sent, so it must say enough to
        recognise the destination -- a bare `gpt-4o` does not distinguish an
        upstream from a proxy pretending to be one.
        """
        ...

    def answer(self, prompt: str) -> str:
        """Answer `prompt`, or raise.

        Raises:
            ModelError: for anything that stops an answer arriving -- a refused
                connection, a timeout, a malformed body, an error status.

        **Never returns an empty string to mean failure.** mamori measured what
        that costs: a pass that degraded to nothing turned a model too slow for
        its timeout into *silence*, and three retries of thirty seconds looked
        exactly like a model too big for the hardware. The same model answered
        in 345 seconds once the timeout was honoured. A failure that returns
        rather than raises is indistinguishable from an answer, which is the
        same ambiguity `ScanError` exists to prevent one layer up.
        """
        ...
