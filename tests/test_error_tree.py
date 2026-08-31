"""An exported exception that nothing raises.

tsumugi found `ContractError` exported, documented, and never raised, and the
reason was structural: the only layer that could raise it was forbidden to
import the module it lived in. **An architecture that forbids keeping the
promise.**

iriguchi's is a different shape and worth naming separately. Nothing forbids
raising it -- the reader it was written for simply does not exist yet. The harm
is the same and it lands on the consumer:

    A caller who writes ``except ContractError:`` gets a branch that looks like
    handling and never runs.

Which is the shape of a check that cannot fail, and that is why this is a test
rather than a cleanup. A one-time tidy would leave the next one to be noticed by
somebody; this notices for them.

**An adapter's exception is not a fossil**, and the first draft of this test said
it was. `EstimationError` is raised by nothing under `src/` because the thing
that raises it is somebody else's estimator -- that is what a port is. What
tells the two apart is not who raises it but **whether anything catches it**:
`routing.py` has an `except EstimationError` that runs, and nothing anywhere
catches a `ContractError`. A dead branch is the harm; a live one is the port
working as designed.

Two directions, because a declaration that is never re-checked rots exactly like
the thing it describes:

- an exception raised by nothing and not declared is a failure
- a declaration for something that *is* raised is stale, and also a failure

Base classes are exempt **only when something actually subclasses them**, and
that is decided from the class tree. A scan that exempted by the name looking
like a base got this wrong here in both directions on the same day: it called
`RoutingError` a base on the strength of its name, which happens to be true, and
would have said the same of a name that had no subclasses at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from iriguchi import errors

SRC = Path(__file__).resolve().parent.parent / "src"


def _exception_classes() -> dict[str, type[BaseException]]:
    """Everything the package exports that a caller could catch."""
    return {
        name: obj
        for name in errors.__all__
        if isinstance(obj := getattr(errors, name), type) and issubclass(obj, BaseException)
    }


def _raised_in_src() -> set[str]:
    """Every name appearing as ``raise Name(...)`` under `src/`.

    Names, not resolved types. A test that resolved them would need to import
    every module to find out, and the question here is what a reader of the
    source sees.
    """
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Raise) and node.exc is not None:
                call = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if isinstance(call, ast.Name):
                    found.add(call.id)
                elif isinstance(call, ast.Attribute):
                    found.add(call.attr)
    return found


def _caught_in_src() -> set[str]:
    """Every name appearing in an ``except`` clause under `src/`.

    This is what separates a port's exception from a fossil. An estimator that
    fails raises `EstimationError` from outside this package -- no line in
    `src/` raises it and the handler still runs. `ContractError` has neither.
    """
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                parts = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                for part in parts:
                    if isinstance(part, ast.Name):
                        found.add(part.id)
                    elif isinstance(part, ast.Attribute):
                        found.add(part.attr)
    return found


def _has_subclasses(cls: type[BaseException], among: dict[str, type[BaseException]]) -> bool:
    """By the tree, not by the name.

    `IriguchiError` and `RoutingError` are genuine bases; a name ending in
    `Error` proves nothing either way.
    """
    return any(other is not cls and issubclass(other, cls) for other in among.values())


@pytest.mark.parametrize("name", sorted(_exception_classes()))
def test_an_exported_exception_is_raised_or_declared_unraised(name: str) -> None:
    """Otherwise it is an invitation to write a branch that never runs."""
    classes = _exception_classes()
    if _has_subclasses(classes[name], classes):
        return
    if name in _raised_in_src() or name in _caught_in_src():
        return
    assert name in errors.NOT_YET_RAISED, (
        f"`{name}` is exported and has a docstring, and nothing under src/ "
        f"raises it or catches it. A caller who writes `except {name}:` gets a "
        f"branch that looks like handling and never runs. Either raise it where "
        f"the event it names happens, give it a handler if an adapter is what "
        f"raises it, or add it to `errors.NOT_YET_RAISED` with the reason -- "
        f"the last is a declaration, and silence is not."
    )


@pytest.mark.parametrize("name", sorted(errors.NOT_YET_RAISED))
def test_a_declaration_of_not_yet_is_still_true(name: str) -> None:
    """A stale exemption is worse than none: it reads as checked."""
    assert name in _exception_classes(), (
        f"`errors.NOT_YET_RAISED` names `{name}`, which is not an exported "
        f"exception. The declaration outlived the thing it described."
    )
    assert name not in _raised_in_src() and name not in _caught_in_src(), (
        f"`{name}` is declared as raised by nothing and reached by nothing, and "
        f"the source now raises or catches it. Delete the declaration -- an "
        f"exemption that has stopped being true still suppresses the check that "
        f"would have said so."
    )


def test_the_reason_says_something() -> None:
    """A declaration whose reason is empty records only that somebody typed."""
    for name, reason in errors.NOT_YET_RAISED.items():
        assert len(reason.split()) >= 10, f"`{name}`'s reason is too short to be one"
