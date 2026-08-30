"""A gate that reports success without checking is worse than no gate.

`Import contracts` in CI ran `python -m importlinter.cli lint-imports` for its
whole life. That form prints nothing and exits 0 whatever the contracts say —
checked against a real `domain -> ports` violation, which the console script
catches with exit 1 and the module form passes in silence.

So the six import contracts were never enforced anywhere but a developer's
machine, including `Only the adapters may know about mamori` — the contract two
of this week's changes were written to protect.

The symptom was visible earlier and dismissed: running the module form in a
throwaway virtualenv produced no output at all, which was noted as odd and let
go because the exit code was 0. **An exit code is only evidence when something
has been shown to make it non-zero.**

This file is a static guard on the invocation. It cannot prove the checker
works, which is the honest limit — proving that needs a deliberate violation,
and a test that mutates the source tree to make one is a worse trade than a
guard on the one thing that silently broke.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"

#: Tools whose `python -m` entry point behaves differently from their console
#: script, or which have no module entry point at all. `import-linter` is the
#: one that bit; the others are here because the failure mode is the same shape
#: and the cost of listing them is a line each.
MODULE_FORM = re.compile(r"python\s+-m\s+(importlinter|import_linter)\b")


def workflow_commands() -> list[str]:
    """Every line that runs something, comments stripped.

    Comments in this workflow discuss `python -m importlinter.cli` and why it is
    wrong, so a naive substring search matches its own explanation. Three guards
    written this week did exactly that; it is worth assuming it will happen
    again.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").split("\n")
    return [line.split("#", 1)[0] for line in lines if line.split("#", 1)[0].strip()]


def test_the_import_contracts_are_actually_run() -> None:
    """The step has to exist before anything else here means anything.

    Verified by *removing* the step, not by changing how it is invoked. That
    distinction cost seven guards in `test_ci_seam_job.py`, which all crashed
    rather than asserting when the job they describe was renamed away -- every
    break-and-watch run against them had injected a changed value and never an
    absence.
    """
    assert any("lint-imports" in line for line in workflow_commands()), (
        "no CI step runs the import contracts. Every other test in this file "
        "describes how that step is invoked, so its absence is the finding."
    )


def test_it_uses_the_console_script_not_the_module_form() -> None:
    """`python -m importlinter.cli` exits 0 on a broken contract, in silence.

    Verified against a real violation rather than assumed:

        $ python -m importlinter.cli lint-imports   ->  (no output)  exit 0
        $ lint-imports                              ->  exit 1, names the import
    """
    offenders = [line.strip() for line in workflow_commands() if MODULE_FORM.search(line)]
    assert not offenders, (
        f"{offenders} runs import-linter through its module entry point, which "
        "prints nothing and exits 0 whatever the contracts say. Use the console "
        "script `lint-imports`."
    )


@pytest.mark.parametrize("tool", ["mypy", "ruff", "pytest"])
def test_the_other_gates_are_present(tool: str) -> None:
    """Not about invocation form — these are checked because a gate silently
    disappearing from the workflow is the same failure with an easier cause."""
    assert any(tool in line for line in workflow_commands()), (
        f"no CI step runs {tool}. A gate that has left the workflow fails the "
        f"same way as one that never worked: silently, and green."
    )
