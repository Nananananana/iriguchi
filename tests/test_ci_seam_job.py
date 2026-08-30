"""The seam job cannot be allowed to quietly do nothing.

`tests/test_mamori_scanner.py` skips entirely when mamori is absent, which is
right. It means the CI job that exists to run it is worthless unless mamori is
genuinely installed there — and a job that installed nothing runs zero tests and
reports success.

That is not hypothetical. tsumugi's equivalent job installs `.[dev,siblings]`,
`siblings` names `mamori`, mamori is not on PyPI, and `continue-on-error: true`
at the job level meant the install failure never turned anything red. The job
looked like coverage of the seam and was coverage of nothing.

So iriguchi's job asserts the sibling is importable before running anything, and
tolerates failure only in the steps *after* that. This file keeps that split from
being undone by somebody who wants a mamori release to stop blocking a merge —
which is a reasonable thing to want, and `continue-on-error` at the job level is
the wrong way to get it. Pin the checkout instead.

Parsed by indentation rather than with a YAML library, so that testing the CI
configuration does not add a dependency to test it with.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"

#: The steps that may fail without failing the job. Everything before them is
#: setup, and setup failing means the job proved nothing.
TOLERANT_STEPS = frozenset({"The seam", "What installing mamori buys, measured here"})


def job_block(name: str) -> list[str]:
    """The lines of one job, by indentation. `jobs:` entries sit at two spaces."""
    lines = WORKFLOW.read_text(encoding="utf-8").split("\n")
    start = next(i for i, line in enumerate(lines) if line == f"  {name}:")
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.strip() and not line.startswith("    "):
            return lines[start:offset]
    return lines[start:]  # pragma: no cover -- only if the job is last in the file


@pytest.fixture(scope="module")
def seam() -> list[str]:
    return job_block("seam")


def test_the_seam_job_exists(seam: list[str]) -> None:
    """Removing it would make every claim about the mamori seam untested in CI
    again, which is the state this job was added to leave."""
    assert seam
    assert any("test_mamori_scanner.py" in line for line in seam)


def test_it_installs_mamori_from_a_checkout(seam: list[str]) -> None:
    """Not from an extra. A manifest naming a package nobody can fetch is a
    broken install rather than an optional feature, which is why there is no
    `siblings` extra to use here."""
    assert any("Nananananana/mamori" in line for line in seam)

    # Comments in this job discuss the `siblings` extra and why there is not
    # one, so look at what actually runs rather than at the word. The first
    # version of this test matched its own explanation.
    commands = [line for line in seam if "pip install" in line and "#" not in line]
    assert commands
    assert not any("siblings" in line for line in commands)


def test_it_refuses_to_run_on_an_absent_sibling(seam: list[str]) -> None:
    """The step that stops this being decoration."""
    assert any("mamori_state" in line for line in seam), (
        "the job must assert the sibling is importable before running tests that "
        "skip when it is not; otherwise a failed install reports success"
    )


def test_the_job_as_a_whole_does_not_tolerate_failure(seam: list[str]) -> None:
    """`continue-on-error` at the job level is what hid tsumugi's broken install.

    Wanting a sibling's release not to block a merge is reasonable. This is the
    wrong lever for it: it also swallows "we could not install the sibling at
    all", and those two are not the same finding. Pin the checkout to a ref.
    """
    job_level = [line for line in seam if line.startswith("    continue-on-error")]
    assert not job_level, (
        "the seam job must not tolerate its own setup failing. If a mamori "
        "release is blocking merges, pin the checkout to a ref instead."
    )


def test_only_the_steps_after_setup_tolerate_failure(seam: list[str]) -> None:
    """Named explicitly, so adding a third tolerant step is a deliberate act."""
    tolerant: list[str] = []
    current = ""
    for line in seam:
        if line.strip().startswith("- name:"):
            current = line.split("- name:", 1)[1].strip()
        elif line.strip() == "continue-on-error: true":
            tolerant.append(current)
    assert set(tolerant) == TOLERANT_STEPS, (
        f"tolerant steps are {sorted(tolerant)}; expected {sorted(TOLERANT_STEPS)}. "
        "A step that may fail silently is a step that may stop checking anything."
    )
