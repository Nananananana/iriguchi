"""Where a prompt can go, and where it ended up.

Two types, deliberately, because they answer different questions.

A ``Destination`` is a place. The set of them is what sensitivity removes from
and what complexity chooses among.

A ``Route`` is an outcome, and it has one member the destinations do not:
``REFUSED``. Refusal is not somewhere a prompt goes -- it is what an empty set
of permitted destinations renders as. Modelling it as a third destination would
make "send it to REFUSED" a sentence the type system permits, and would let a
future filter "remove" it, which is meaningless.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["Destination", "Route"]


class Destination(Enum):
    """Somewhere a prompt could be sent.

    A closed set. A third destination -- a second local model, a different
    provider -- is a change to the routing contract and has to be argued in an
    ADR, because every rule that removes destinations was written knowing how
    many there were.
    """

    #: A model on this machine. Nothing leaves.
    LOCAL = "local"
    #: An external service, reached through mamori, which protects the text on
    #: the way out and restores it on the way back. iriguchi never sends raw
    #: text anywhere itself.
    EXTERNAL = "external"


class Route(Enum):
    """What was decided."""

    LOCAL = "local"
    EXTERNAL = "external"
    #: No destination survived. Nothing runs, and the person is told why.
    REFUSED = "refused"

    @classmethod
    def for_destination(cls, destination: Destination) -> Route:
        """The route that sends a prompt to `destination`."""
        return cls(destination.value)
