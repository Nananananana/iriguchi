"""Every `IriguchiError` subclass in the package, found by walking it.

**This exists because two separate checks both narrowed the same claim.**

`tests/test_error_tree.py` asked `errors.__all__` for "everything a caller could
catch". `tests/test_the_error_catalogue_is_complete.py` asked `vars(errors)` for
"every exception to account for". Both sentences are about the package; both
implementations were about one module.

`InteropError` lived in `iriguchi.interop.presidio`. It is raised on the
`--findings` path -- the seam a sibling's analyzer output crosses -- it exits 1,
and it reaches a person's terminal:

    $ iriguchi route --findings bad.json "hello world"
    InteropError: result 0: span start must not be negative, got -1

It was in neither check, so `iriguchi errors` published a catalogue that claimed
to be complete and was missing a printable kind. Sora's acceptance condition for
that document was, in their words, *every kind that can be printed appears* --
and the check written to guarantee it could not see one directory sideways.

The class has moved into `iriguchi.errors`, which makes both of the old scans
accidentally correct again. That is the trap: accidentally correct is how this
got here. So the scan is package-wide now, in one place, used by both.
"""

from __future__ import annotations

import importlib
import pkgutil

import iriguchi
from iriguchi.errors import IriguchiError

__all__ = ["every_subclass", "modules_walked"]


def _modules() -> list[str]:
    found = [iriguchi.__name__]
    for module in pkgutil.walk_packages(iriguchi.__path__, f"{iriguchi.__name__}."):
        found.append(module.name)
    return found


def modules_walked() -> list[str]:
    """Every module the walk imports. Exposed so a test can assert the walk is
    wider than one file rather than trusting that it is."""
    walked = []
    for name in _modules():
        try:
            importlib.import_module(name)
        except ImportError:
            # An adapter whose optional dependency is absent. That is the
            # normal state in CI for mamori and presidio, and skipping it here
            # is correct: a class that cannot be imported cannot be raised.
            continue
        walked.append(name)
    return walked


def every_subclass() -> dict[str, type[IriguchiError]]:
    """Name to class, for every `IriguchiError` subclass defined anywhere.

    Keyed on the class name rather than the qualified path, because that is what
    a consumer sees: the name before the colon on the first line of stderr.
    """
    found: dict[str, type[IriguchiError]] = {}
    for name in modules_walked():
        module = importlib.import_module(name)
        for attribute, value in vars(module).items():
            if (
                isinstance(value, type)
                and issubclass(value, IriguchiError)
                and value is not IriguchiError
            ):
                found.setdefault(value.__name__, value)
                del attribute
    return found
