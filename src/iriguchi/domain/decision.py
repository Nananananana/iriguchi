"""What came out of the deciding path.

A `RoutingDecision` is the whole answer, not just the route. It carries both
axes as they were computed -- including the one that changed nothing, because
"complexity said HIGH and it did not matter" is information a person needs --
and two accounts: what happened, and what stopped happening.

It is a value. Nothing here reaches a scanner, a model or a socket; it is what
the policy returns after everything has already been decided.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .complexity import Complexity
from .destination import Route
from .reason import Reason, Removal
from .sensitivity import Sensitivity

__all__ = ["RoutingDecision"]


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Where a prompt is going, and the whole account of why."""

    route: Route
    #: The veto axis, as it was computed. Reported even when it removed nothing.
    sensitivity: Sensitivity
    #: The preference axis, as it was computed. Reported even when the veto had
    #: already settled the answer -- a decision that hides the axis it ignored
    #: cannot be checked against the one that did the work.
    complexity: Complexity
    #: What happened, in a stable order.
    reasons: tuple[Reason, ...] = field(default=())
    #: What stopped happening. Empty when nothing was taken away, which is not
    #: the same as nothing having been available -- see the reasons for that.
    removed: tuple[Removal, ...] = field(default=())

    @property
    def was_refused(self) -> bool:
        return self.route is Route.REFUSED

    @property
    def leaves_the_machine(self) -> bool:
        """The question everything else exists to answer correctly."""
        return self.route is Route.EXTERNAL
