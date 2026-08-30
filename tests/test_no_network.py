"""That the poisoning in `conftest.py` actually poisons anything.

A guard nobody checks is a guard that silently stops working, and this one is
load-bearing: every other test in the suite is only evidence about the network
because this fixture is doing something. So the fixture is tested like any other
code -- by making it fail on purpose.

The last test is the one the project is about. A full routing decision, on a
prompt with something sensitive in it, on a machine where reaching for a socket
raises: the decision still completes, and it does not leave.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

# `tests/` is deliberately not a package (AGENTS.md: duplicate basenames break
# collection), so this is the sibling-module import pytest's default
# `prepend` import mode makes available.
from conftest import NetworkAccessError
from iriguchi.domain.complexity import Complexity, Signal, SignalKind
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.policy import RoutingPolicy
from iriguchi.domain.sensitivity import Finding, Sensitivity
from iriguchi.domain.span import Span


class TestThePoisonWorks:
    def test_opening_a_socket_raises(self) -> None:
        with pytest.raises(NetworkAccessError):
            socket.socket()

    def test_resolving_a_name_raises(self) -> None:
        with pytest.raises(NetworkAccessError):
            socket.getaddrinfo("example.invalid", 443)

    def test_connecting_raises(self) -> None:
        with pytest.raises(NetworkAccessError):
            socket.create_connection(("example.invalid", 443))

    def test_it_reaches_code_that_never_names_a_socket(self) -> None:
        """The reason this is a runtime fixture and not only an import contract.

        Nothing here imports `socket`. `urllib` does, several layers down, and
        an import contract that watched this file would see nothing wrong.
        """
        with pytest.raises(NetworkAccessError):
            urllib.request.urlopen("https://example.invalid/", timeout=0.01)

    def test_it_is_not_catchable_as_an_ordinary_failure(self) -> None:
        """Fail-closed code is entitled to catch `OSError` and fall back.

        That is exactly the behaviour worth catching in a router whose promise
        is that it did not use the network, so the poison is not an `OSError`.
        """
        assert not issubclass(NetworkAccessError, OSError)
        with pytest.raises(NetworkAccessError):
            try:
                socket.socket()
            except OSError:  # pragma: no cover -- the point is that this misses
                pytest.fail("an OSError handler swallowed the poison")


@pytest.mark.network
class TestOptingOut:
    """v0.2's adapters will need this. It exists now so the escape hatch is
    designed rather than improvised under pressure."""

    def test_the_marker_restores_the_real_socket(self) -> None:
        assert socket.socket is not None
        assert socket.socket.__module__ == "socket"


class TestDecidingNeedsNoNetwork:
    """The claim the whole project rests on, as a test rather than a promise."""

    def test_a_full_decision_completes_with_the_network_unavailable(self) -> None:
        sensitivity = Sensitivity.from_findings(
            (Finding("fallback.email-shape", "fallback", Span(4, 22)),)
        )
        complexity = Complexity.from_signals(
            (Signal("complexity.enormous", SignalKind.LEXICAL, 0.95),)
        )
        decision = RoutingPolicy().decide(sensitivity, complexity, frozenset(Destination))

        assert decision.route is Route.LOCAL
        assert not decision.leaves_the_machine
        assert decision.removed
