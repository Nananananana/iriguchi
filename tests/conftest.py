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


def _network_error(name: str) -> NetworkAccessError:
    return NetworkAccessError(
        f"{name} was called during a test. Nothing in iriguchi may reach the "
        "network: the routing decision is made before anything is sent, and the "
        "deciding path has no way to send (ADR-0004). If this is a v0.2 adapter "
        "test that genuinely needs a socket, mark it @pytest.mark.network."
    )


def _refuse(name: str) -> Any:
    def refuser(*args: object, **kwargs: object) -> NoReturn:
        raise NetworkAccessError(
            f"{name} was called during a test. Nothing in iriguchi may reach the "
            "network: the routing decision is made before anything is sent, and the "
            "deciding path has no way to send (ADR-0004). If this is a v0.2 adapter "
            "test that genuinely needs a socket, mark it @pytest.mark.network."
        )

    return refuser


def _refusing_socket(original: type[socket.socket]) -> type[socket.socket]:
    """A socket class that refuses to connect, rather than a function.

    **`socket.socket` is a class and `ssl` subclasses it.** Replacing it with a
    function made `import ssl` raise `TypeError: function() argument 'code' must
    be code, not str` -- so any code importing the network stack *during* a test
    died at import, whatever it was going to do with it. The fence was blocking
    the module rather than the connection.

    Found when the public `route()` began importing its config lazily: the
    import happened inside a fenced test instead of at collection, and nine
    tests failed somewhere none of them mentions.

    Subclassing keeps the block exactly as strong. Nothing here can open a
    connection; a socket that is never connected reaches nothing, and the
    refusal now fires at the moment somebody tries rather than at the moment
    they allocate.
    """

    class Refusing(original):  # type: ignore[valid-type, misc]
        def __init__(self, *args: object, **kwargs: object) -> NoReturn:
            """Constructing one still raises, as it did before.

            **Subclassing does not call `__init__`**, so `class SSLSocket(socket)`
            at import time is fine while `socket.socket()` is not. That is the
            whole difference between blocking a module and blocking a use, and
            it keeps `test_opening_a_socket_raises` true rather than relaxing it
            to make an import work.
            """
            raise _network_error("socket.socket")

    # `type: ignore` because mypy reads a class whose `__init__` is `NoReturn`
    # as uninstantiable and therefore not a `type[socket]`. That is exactly what
    # it is for, and the annotation is the honest one for the caller.
    return Refusing  # type: ignore[return-value]


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
    # `type: ignore` because `socket.socket` is a class and mypy is right
    # that assigning to one is unusual. Replacing it for the length of a
    # test is the whole mechanism, and `ruff` rewrote the `setattr` form
    # that used to hide this -- the rewrite is an improvement and the
    # silenced complaint is the honest cost of it.
    socket.socket = _refusing_socket(saved["socket"])  # type: ignore[misc]
    for name in ("create_connection", "getaddrinfo"):
        setattr(socket, name, _refuse(f"socket.{name}"))
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(socket, name, original)
