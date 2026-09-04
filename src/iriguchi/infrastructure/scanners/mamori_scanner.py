"""mamori as a `SensitivityScanner`. The adapter ADR-0005 promised.

The fallback scanner misses 67.3% of mamori's own labelled corpus -- names
without an honorific, English names, companies, addresses. This is what closes
that, and it is the only file in iriguchi allowed to name `mamori`
(`mamori-is-an-adapter`, asserted by `import-linter` and by
`tests/test_architecture.py`).

**Optional.** iriguchi declares zero runtime dependencies and keeps them. Import
this module without mamori installed and it raises at construction with a
sentence saying what to install -- not at import, so that `iriguchi doctor` can
say mamori is absent without the tool failing to start.

Three decisions are worth reading before changing anything here.

**It asks mamori with a permissive policy, as mamori's own `inspect` does.**
mamori's default policy *blocks* on a credential, which would arrive here as an
exception and become "the scanner broke". The route would be the same -- local
-- and the reason would be wrong, and a wrong reason is worse than a missing one
because it reads as authoritative. Under a permissive policy mamori *reports* the
credential and iriguchi's own policy decides what it means. A scanner proposes;
that is the whole of ADR-0005.

**It carries no `preview`, no `confidence` and no detector name into a
`Finding`.** `EntityReport.preview` is a masked form of the original, and
mamori's own ADR-0032 says plainly that masked is not absent. A confidence and a
detector id describe how a value was found, which is a statement about the
value. `Finding` has nowhere to put any of them, which is not an accident.

**Every scan gets a fresh session and store, and closes it.** `session.protect`
allocates placeholders into a mapping store, and a mapping is the highest-value
object mamori has. iriguchi is asking a question, not protecting anything -- so
whatever gets allocated is discarded immediately rather than accumulating in a
long-lived store belonging to a routing decision that may end in a refusal.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from enum import Enum

from ...domain.sensitivity import Finding
from ...domain.span import Span
from ...errors import ScanError

__all__ = ["MamoriScanner", "SiblingState", "mamori_is_available", "mamori_state"]


class SiblingState(Enum):
    """Three states, because two of them mean opposite things to a test.

    `mamori_is_available()` used to answer this with a boolean, and the boolean
    conflated the first two. Both raise `ImportError`; only one of them is
    somebody's ordinary configuration.

    The failure that shape produces is silence. A test suite gated on "is it
    available" skips its entire sibling seam when the sibling is *broken*, and
    reports green -- so the one place that checks the seam goes quiet exactly
    when the seam has moved. akashi found this class of bug in its own drift
    check, where an `HTTPError` was being swallowed as a connection failure and
    a 404 passed as "cannot reach".
    """

    #: Not installed. iriguchi is designed to work like this, and a test that
    #: needs the seam should skip.
    ABSENT = "absent"
    #: Installed, and importing it fails. **A finding, never a skip.** Something
    #: is wrong with an environment somebody meant to have working.
    BROKEN = "broken"
    AVAILABLE = "available"


#: What to tell somebody who has not installed it.
#:
#: **The sentence has to say it is not published.** This comment already said
#: "not on PyPI yet, so the instruction is a checkout rather than a package
#: name" and the string somebody actually reads did not, which left a reader to
#: try `pip install mamori`, get a 404, and conclude the advice was stale.
#: A remedy that names a relative path without saying why is a remedy that looks
#: like a typo.
_MISSING = (
    "mamori is not installed. iriguchi works without it -- the built-in fallback "
    "scanner is the default -- but the fallback misses names without an honorific, "
    "English names, company names and addresses. mamori is not on PyPI, so it "
    "needs a checkout beside this one: `uv pip install -e ../mamori`."
)


def mamori_state() -> tuple[SiblingState, str]:
    """Which of the three, and the detail when there is one.

    `find_spec` answers "is it installed" without running the package, so the
    two `ImportError` cases separate. It can raise on its own account -- a
    broken path entry, a finder that objects -- and that is not absence either.
    """
    try:
        installed = importlib.util.find_spec("mamori") is not None
    except (ImportError, ValueError) as failure:
        return SiblingState.BROKEN, f"looking for mamori failed: {failure}"

    if not installed:
        return SiblingState.ABSENT, ""

    try:
        import mamori  # noqa: F401
    except Exception as failure:
        return SiblingState.BROKEN, f"{type(failure).__name__}: {failure}"
    return SiblingState.AVAILABLE, ""


def mamori_is_available() -> bool:
    """Whether the adapter can be constructed.

    What `iriguchi doctor` asks, and a boolean is the right answer to *that*
    question -- an environment where mamori is broken can no more use it than
    one where mamori is absent. Anything that needs to tell the two apart wants
    `mamori_state()`, and a test gate always does.
    """
    return mamori_state()[0] is SiblingState.AVAILABLE


class MamoriScanner:
    """Sensitivity findings from mamori, with nothing else attached."""

    name = "mamori"

    def __init__(self) -> None:
        state, detail = mamori_state()
        if state is SiblingState.ABSENT:
            raise ScanError(_MISSING)
        if state is SiblingState.BROKEN:
            # Telling somebody to install what they already have is the
            # `policy.prefer-local` mistake again: a wrong stated reason reads
            # as authoritative, and sends them to fix the wrong thing.
            raise ScanError(
                f"mamori is installed and cannot be imported ({detail}). This is not "
                "the same as it being absent -- something is wrong with an environment "
                "you meant to have working, so iriguchi is refusing rather than "
                "quietly using the fallback."
            )

        from mamori import PrivacyPolicy

        # Permissive so that a credential is *reported* rather than refused.
        # mamori's default policy blocks it, and a block here would become "the
        # scanner broke" -- the same route for the wrong stated reason.
        self._policy = PrivacyPolicy.permissive()

    def scan(self, text: str) -> Sequence[Finding]:
        """Everything mamori finds, as spans into `text`.

        mamori normalizes internally and maps its spans back before reporting
        (its ADR-0004), so the offsets arriving here are already in the
        coordinates of the string that was passed in. The conformance suite
        checks that rather than trusting it.
        """
        if not text:
            return ()

        try:
            from mamori import PrivacySession
            from mamori.infrastructure.storage.memory import InMemoryMappingStore

            with PrivacySession(policy=self._policy, store=InMemoryMappingStore()) as session:
                reports = session.protect(text).entities
        except Exception as failure:
            # Anything at all. A scanner that returns nothing to signal failure
            # is the one thing the port forbids, because the caller cannot tell
            # that from "nothing here" -- and only one of those is safe.
            raise ScanError(f"mamori could not scan: {type(failure).__name__}: {failure}") from (
                failure
            )

        findings = [
            Finding(
                rule=f"mamori.{report.entity_type.lower()}",
                source=self.name,
                span=Span(report.span.start, report.span.end),
            )
            for report in reports
        ]
        findings.sort(key=lambda finding: (finding.span, finding.rule))
        return tuple(findings)
