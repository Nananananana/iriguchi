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

from collections.abc import Sequence

from ...domain.sensitivity import Finding
from ...domain.span import Span
from ...errors import ScanError

__all__ = ["MamoriScanner", "mamori_is_available"]

#: What to tell somebody who has not installed it. Not on PyPI yet, so the
#: instruction is a checkout rather than a package name.
_MISSING = (
    "mamori is not installed. iriguchi works without it -- the built-in fallback "
    "scanner is the default -- but the fallback misses names without an honorific, "
    "English names, company names and addresses. Install it from a checkout: "
    "`uv pip install -e ../mamori`."
)


def mamori_is_available() -> bool:
    """Whether the adapter can be constructed.

    Used by `iriguchi doctor`, which has to be able to say mamori is absent
    without that being an error.
    """
    try:
        import mamori  # noqa: F401
    except ImportError:
        return False
    return True


class MamoriScanner:
    """Sensitivity findings from mamori, with nothing else attached."""

    name = "mamori"

    def __init__(self) -> None:
        try:
            from mamori import PrivacyPolicy
        except ImportError as missing:  # pragma: no cover -- needs mamori absent
            raise ScanError(_MISSING) from missing

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
