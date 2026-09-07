"""A `route` must not pay for `ask`, `eval` and `schema`.

Sora spawns iriguchi **once per prompt**. So the cost a consumer actually pays
is not the 0.044 ms decision, it is the whole process — and the composition root
imported every command's dependencies before deciding which command was running.

Measured on this machine, minimum of eleven runs:

    bare interpreter    54.2 ms
    route              179.5 ms   -> iriguchi's own cost: 125.3 ms
    route (after)      148.1 ms   ->                       95.1 ms

The four that were paid for and unused by a `route`:

    iriguchi.application.asking      ~20 ms   only `ask`
    iriguchi.evaluation.scoring      ~11 ms   only `eval`
    iriguchi.evaluation.dataset               only `eval`
    importlib.resources              ~15 ms   only `schema`, via contract.py

A second round found more, after this file's own docstring had said there was
nothing cheap left. **`pathlib`** was imported at the top of `main.py` for two
lines inside command-specific helpers, and it drags `ipaddress`,
`urllib.parse` and `fnmatch` with it. The mamori scanner was imported for three
names used by `config` alone. Seven modules, ~8 ms of import work:

    pathlib + ipaddress + urllib.parse + fnmatch    only --findings and --corpus
    iriguchi.infrastructure.scanners.mamori_scanner only `config`

`importlib.resources` was the expensive one and the least visible: `contract.py`
imported it at module scope for a single function, and it drags `inspect` along.

**The same change moves three numbers, because they are one cause.** A module
that is imported costs time to import, memory to hold, and an entry in
`sys.modules`:

    iriguchi's own startup cost   125.3 ms -> 95.1 ms    (-24%)
    retained after one route      5017 KiB -> 4079 KiB   (-19%)
    modules loaded                     172 -> 146 -> 132

Milliseconds are not asserted anywhere here -- a timing test on a shared runner
teaches everybody to ignore the suite. The module count is the same fact,
measured in a unit that does not move between machines.

**This file is the mechanism, and without it the change is a comment.** An
`import` added at the top of `main.py` for a reader's convenience puts the cost
straight back, produces no test failure anywhere else, and would be found by
nobody -- performance regressions are silent by construction, which is what they
have in common with the stale numbers and unchecked claims this suite is mostly
about.

## What is deliberately not chased

`dataclasses` costs ~17 ms and brings `inspect` with it. Every domain value is a
frozen dataclass and hand-writing them to save that would be a bad trade, so
`inspect` stays loaded and this file says why rather than leaving somebody to
rediscover it. `typing` is ~15 ms and is real at runtime for the ports.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

#: Modules a `route` must not load, and who actually needs each.
UNUSED_BY_ROUTE = {
    "iriguchi.application.asking": "only `ask`",
    "pathlib": "only `--findings` and `--corpus`; it drags in ipaddress and urllib",
    "ipaddress": "nothing here wants it; `pathlib` brought it",
    "urllib.parse": "nothing here wants it; `pathlib` brought it",
    "iriguchi.infrastructure.scanners.mamori_scanner": "only `config`",
    "iriguchi.evaluation.scoring": "only `eval`",
    "iriguchi.evaluation.dataset": "only `eval`",
    "importlib.resources": "only `schema`, via interfaces/contract.py",
}

#: Loaded, and named here so that its cost is a recorded decision rather than an
#: oversight somebody re-measures in a year.
KNOWN_COST = ("dataclasses", "inspect", "typing", "re")


def _modules_after(argv: list[str]) -> set[str]:
    """Every module loaded in a fresh interpreter that ran `argv`.

    A subprocess rather than an import inside the test process, because pytest
    has already imported half the package by the time any test runs. That is
    exactly the shape of measurement this file exists to prevent, so measuring
    it wrongly here would be an unusually poor joke.
    """
    probe = (
        "import sys, json;"
        "import iriguchi.interfaces.cli.main as m;"
        f"m.main({argv!r});"
        "print('MODULES', json.dumps(sorted(sys.modules)))"
    )
    result = subprocess.run(  # noqa: S603 - sys.executable and a literal probe
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1", "IRIGUCHI_LOCAL": "1", "IRIGUCHI_EXTERNAL": "1"},
    )
    assert result.returncode == 0, result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("MODULES "))
    import json as _json

    return set(_json.loads(line[len("MODULES ") :]))


@pytest.fixture(scope="module")
def after_a_route() -> set[str]:
    loaded = _modules_after(["route", "hello"])
    assert "iriguchi.application.routing" in loaded, (
        "the probe did not actually route, so every assertion below is about nothing"
    )
    return loaded


class TestARouteDoesNotPayForTheOtherCommands:
    @pytest.mark.parametrize("module", sorted(UNUSED_BY_ROUTE), ids=sorted(UNUSED_BY_ROUTE))
    def test_it_is_not_loaded(self, module: str, after_a_route: set[str]) -> None:
        assert module not in after_a_route, (
            f"{module} is loaded by a plain `route` and is {UNUSED_BY_ROUTE[module]}. "
            f"Something imported it at module scope again."
        )

    def test_the_commands_that_need_them_still_work(self) -> None:
        """Deferring an import is only free if the deferred thing still
        arrives. Each of these is the command whose dependency was moved."""
        assert "iriguchi.evaluation.scoring" in _modules_after(["eval"])
        assert "importlib.resources" in _modules_after(["schema"])


class TestTheCostThatStays:
    @pytest.mark.parametrize("module", KNOWN_COST)
    def test_it_is_still_loaded_and_that_is_recorded(
        self, module: str, after_a_route: set[str]
    ) -> None:
        """The inverse direction, and it is not pedantry.

        If one of these ever stops being loaded, this repository has become
        measurably cheaper for a reason nobody wrote down -- and the docstring
        above, which tells the next person not to bother chasing it, has become
        wrong. Failing here is the cheapest way to notice.
        """
        assert module in after_a_route


class TestTheModuleCountIsTheBudget:
    """A ceiling, in the one unit that does not move between machines.

    Time is the thing anybody cares about and the thing no test can assert
    without becoming flaky on a busy runner. Module count is the same fact --
    every module costs time to import, memory to hold, and a `sys.modules`
    entry -- and it is exactly reproducible.

    The number is a **budget, not a measurement**: loose enough that an honest
    new import does not fail it, tight enough that re-importing `asking`,
    `scoring` and `importlib.resources` at module scope does.
    """

    #: 132 now: 172 -> 146 when the composition root stopped importing every
    #: command, then -> 132 when `pathlib` and the mamori scanner followed. The
    #: ceiling came down with it, because the test below insists it does.
    CEILING = 140

    def test_a_route_stays_under_the_budget(self, after_a_route: set[str]) -> None:
        assert len(after_a_route) <= self.CEILING, (
            f"a `route` now loads {len(after_a_route)} modules, over the {self.CEILING} "
            f"budget. Something was imported at module scope that a route does not "
            f"need -- or the budget needs raising on purpose, with a reason."
        )

    def test_the_budget_is_not_slack(self, after_a_route: set[str]) -> None:
        """A ceiling nothing approaches is a ceiling that would not catch the
        regression it exists for. This fails if the real count drifts far below
        the budget, which means the budget should come down with it."""
        assert len(after_a_route) >= self.CEILING - 25, (
            f"only {len(after_a_route)} modules load, well under the {self.CEILING} "
            f"budget. Lower the budget so it still catches something."
        )


class TestTheDeferredImportsAreRealDeferrals:
    """A lazy import inside a function is only lazy if the module does not also
    import it at the top. Both spellings satisfy every other test here."""

    def test_main_does_not_import_them_at_module_scope(self) -> None:
        import ast
        from pathlib import Path

        source = Path(__file__).resolve().parent.parent / "src/iriguchi/interfaces/cli/main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        top_level: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module)
            elif isinstance(node, ast.Import):
                top_level.update(alias.name for alias in node.names)
        forbidden = {"...application.asking", "...evaluation.scoring", "...evaluation.dataset"}
        # `ast` records relative imports without the dots, so compare on the tail.
        offenders = {
            name for name in top_level if any(name.endswith(f.lstrip(".")) for f in forbidden)
        }
        assert not offenders, f"back at module scope in main.py: {sorted(offenders)}"

    def test_contract_does_not_import_resources_at_module_scope(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parent.parent / "src/iriguchi/interfaces/contract.py"
        lines = source.read_text(encoding="utf-8").splitlines()
        top_level = [line for line in lines if line.startswith("import importlib")]
        assert not top_level, "importlib.resources is back at module scope in contract.py"
