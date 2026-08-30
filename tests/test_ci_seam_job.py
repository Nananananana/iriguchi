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

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"

#: A forty-character hex sha, and nothing looser. A branch name or a tag both
#: move, and a moving ref is what makes a re-run able to turn red into green.
PINNED_REF = re.compile(r"^\s+ref:\s+[0-9a-f]{40}(?:\s|$)")


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
    assert any("pytest" in line for line in seam)


def test_it_runs_the_whole_suite_rather_than_named_files(seam: list[str]) -> None:
    """A step that enumerates files drifts the moment a file is added.

    This job first ran `tests/test_mamori_scanner.py`, the only mamori-gated
    file at the time. `tests/test_escalation_channel.py` then arrived, skipped
    everywhere else, and ran nowhere at all -- the silence this job exists to
    remove, reintroduced by the fix for it.

    The other jobs run this suite without mamori and this one runs it with. The
    difference between them is the seam, and nothing has to be kept in step.
    """
    runs = [line for line in seam if "pytest" in line and "#" not in line]
    assert runs, "the seam job must run the tests"
    named = [line for line in runs if "tests/" in line or "tests\\" in line]
    assert not named, (
        f"{named} names files. Run the whole suite: this job's value is that it "
        "runs with mamori present, and a list of files stops being complete the "
        "first time somebody adds a mamori-gated test."
    )


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


def test_the_sibling_is_pinned_to_a_commit(seam: list[str]) -> None:
    """Unpinned, this job's answer depends on when it ran.

    A re-run that turns red into green is not a check. And the bump commit is
    the notification the family otherwise has no mechanism for: six libraries
    moving independently means a producer can move without anybody noticing,
    and raising this sha turns that into something somebody has to look at.

    A branch or a tag would not do. Both move.
    """
    assert any(PINNED_REF.match(line) for line in seam), (
        "the sibling checkout must name a full commit sha. A branch or a tag "
        "moves, and then a re-run can turn this job green without anything "
        "here having changed."
    )


def test_nothing_in_the_job_tolerates_failure(seam: list[str]) -> None:
    """The pin removes the need for tolerance rather than covering it up.

    An earlier version let the seam step fail without failing the job, so that
    a mamori release could not block an unrelated merge. With the sha pinned a
    mamori release cannot reach this job at all, so a failure means *iriguchi*
    broke the seam against a sibling that has not moved — which is precisely
    the finding that should stop a merge.

    `continue-on-error` at the job level is also what let tsumugi's equivalent
    spend an unknown period failing to install mamori while reporting success.
    """
    # Comment lines in this job explain why there is no `continue-on-error`,
    # so match what YAML would read rather than what the file contains. Three
    # separate guards today have matched their own explanation; the shape to
    # watch for is a check whose subject includes the prose about the check.
    tolerant = [
        line for line in seam if line.split("#", 1)[0].strip().startswith("continue-on-error")
    ]
    assert not tolerant, (
        f"{len(tolerant)} step(s) tolerate failure. With the sibling pinned there "
        "is nothing left for tolerance to protect against: raise the pin instead."
    )
