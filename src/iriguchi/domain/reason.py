"""Why, and why not.

A router that returns a route is a router nobody can debug and nobody can
trust. "It went local" does not answer "why did it go local", and that question
gets asked every time the answer is worse than expected (ADR-0006).

So a decision carries two accounts. ``Reason`` says what happened. ``Removal``
says what stopped happening, and which destination it stopped for. The second is
the half that normally gets dropped, and it is the half a person needs: knowing
a prompt stayed local is useless without knowing that the alternative was
removed by a token at offset 40.

Neither carries a matched value. ``detail`` is prose about a rule -- what it
looked for, what it measured, where it fired -- and a sentence that quotes the
text it fired on has undone the point of the project. Nothing enforces that at
the type level, because a string field cannot be made value-free by typing; it
is enforced by review, by the rule in AGENTS.md, and by a test that renders
these objects and greps them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .destination import Destination
from .span import Span

__all__ = ["Reason", "Removal"]


@dataclass(frozen=True, slots=True)
class Reason:
    """One rule, and what it had to say."""

    #: Namespaced, and stable: `fallback.key-shape`, `complexity.multi-step`,
    #: `policy.no-destination-available`. An id is what lets somebody disable a
    #: rule without forking the library, and what lets this object name it.
    rule: str
    #: Which scanner, estimator or policy produced it. Two scanners can fire on
    #: the same span for different reasons, and a person reading an explanation
    #: needs to know whether they are looking at the deliberately-dumb fallback
    #: or at mamori (ADR-0005).
    source: str
    #: Where, or ``None`` for a rule that is not about a place in the text --
    #: "no local model is configured" is true of the machine, not of a span.
    span: Span | None
    #: Prose, for a person. Naming the rule is not the same as explaining it,
    #: and an explanation nobody can read is not an explanation.
    detail: str

    def __post_init__(self) -> None:
        if not self.rule:
            raise ValueError("a reason must name the rule that produced it")
        if not self.detail:
            raise ValueError(f"rule {self.rule!r} produced a reason with no detail")

    @property
    def sort_key(self) -> tuple[int, int, str, str]:
        """Total, and stable across runs.

        Reasons without a span sort first, because they are statements about
        the request as a whole and a reader wants those before the per-span
        detail. Ties break on the rule id, which is unique enough in practice
        and deterministic when it is not.
        """
        if self.span is None:
            return (-1, -1, self.source, self.rule)
        return (self.span.start, self.span.end, self.source, self.rule)


@dataclass(frozen=True, slots=True)
class Removal:
    """A destination that was taken off the table, and what took it."""

    destination: Destination
    reason: Reason
