"""What the scaffold promises, asserted.

There is no routing code yet, so there is very little to test. What there is,
is the set of claims the scaffold itself makes: the version is one thing and not
two, the exception tree means what ``errors.py`` says it means, and the layer
packages the import contracts are written against actually exist.

The last one matters more than it looks. ``.importlinter`` names packages by
string, and a contract whose source module does not exist is a contract that
passes without checking anything.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

import iriguchi
from iriguchi.errors import (
    ConfigurationError,
    ContractError,
    EstimationError,
    IriguchiError,
    RoutingError,
    ScanError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Every layer named in the table in AGENTS.md and in the import contracts.
LAYERS = (
    "iriguchi.domain",
    "iriguchi.ports",
    "iriguchi.application",
    "iriguchi.infrastructure",
    "iriguchi.evaluation",
    "iriguchi.interfaces",
    "iriguchi.interfaces.cli",
    "iriguchi.errors",
)


def test_the_version_is_declared_once() -> None:
    """``pyproject.toml`` and ``__init__.py`` agree, or the wheel lies."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        declared = tomllib.load(handle)["project"]["version"]
    assert iriguchi.__version__ == declared


@pytest.mark.parametrize("name", LAYERS)
def test_every_layer_the_contracts_name_exists(name: str) -> None:
    """A contract whose source module is missing checks nothing."""
    assert importlib.import_module(name) is not None


@pytest.mark.parametrize("failure", [ScanError, EstimationError])
def test_a_failed_proposal_is_a_routing_failure(failure: type[Exception]) -> None:
    """ADR-0002.

    A scanner that died has not reported "nothing sensitive", it has reported
    nothing at all. Both are ``RoutingError`` so that no caller can mistake the
    second for the first and send the text anyway.
    """
    assert issubclass(failure, RoutingError)


@pytest.mark.parametrize(
    "error", [RoutingError, ScanError, EstimationError, ConfigurationError, ContractError]
)
def test_everything_raised_is_catchable_as_one_thing(error: type[Exception]) -> None:
    assert issubclass(error, IriguchiError)


def test_a_configuration_problem_is_not_a_routing_failure() -> None:
    """They are answered differently.

    A routing failure means this prompt got no decision. A configuration
    problem means no prompt will get one until a person fixes something, and a
    caller that retries the first would loop forever on the second.
    """
    assert not issubclass(ConfigurationError, RoutingError)
    assert not issubclass(ContractError, RoutingError)
