"""The network, made unavailable to the whole suite.

`import-linter`'s `no-network` contract and `tests/test_architecture.py` between
them prove that nothing *imports* a socket. This proves that nothing *calls*
one, which is a different claim: an import contract cannot see a call reached
through a library, a lazily-imported module, or anything else that arrives at
`socket.socket` without the string appearing in this repository.

Through v0.1 there is no outbound path at all, so the poisoning is autouse and
applies everywhere. That is a stronger guarantee than a fixture individual tests
opt into: any code that reaches for the network fails, in every test, without
anyone having remembered to check.

When v0.2 adds the escalation channel and the local-model adapter, they opt out
with `@pytest.mark.network` rather than the default being relaxed. Making the
exception visible per test is the whole point -- a suite where the network is
available by default cannot tell you anything about a router whose central
promise is that it did not use it.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any, NoReturn

import pytest


class NetworkAccessError(AssertionError):
    """Something reached for the network. In this suite that is always a bug.

    An `AssertionError` rather than an `OSError`, deliberately: code under test
    is entitled to catch `OSError` and fall back to something, and a fail-closed
    router that quietly degrades when the network is missing is precisely the
    behaviour these tests exist to catch. This is not catchable by anything
    reasonable.
    """


def _refuse(name: str) -> Any:
    def refuser(*args: object, **kwargs: object) -> NoReturn:
        raise NetworkAccessError(
            f"{name} was called during a test. Nothing in iriguchi may reach the "
            "network: the routing decision is made before anything is sent, and the "
            "deciding path has no way to send (ADR-0004). If this is a v0.2 adapter "
            "test that genuinely needs a socket, mark it @pytest.mark.network."
        )

    return refuser


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest) -> Iterator[None]:
    """Replace every entry point to the network with one that raises.

    Patched by name on the `socket` module rather than by blocking a port, so a
    test does not have to guess where something would have connected to. The
    three named here are the ways a Python program actually opens a connection;
    everything higher up -- `urllib`, `http.client`, an SDK -- goes through one
    of them.
    """
    if request.node.get_closest_marker("network"):
        yield
        return

    saved = {name: getattr(socket, name) for name in ("socket", "create_connection", "getaddrinfo")}
    for name in saved:
        setattr(socket, name, _refuse(f"socket.{name}"))
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(socket, name, original)
