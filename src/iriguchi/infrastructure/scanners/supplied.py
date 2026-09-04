"""A scanner that reports what it was handed.

Somebody who already runs Presidio, or a detector this project has never heard
of, has findings before iriguchi is involved. `SuppliedScanner` is how those
reach the veto without iriguchi importing anything to get them.

**It ignores the text.** That is the whole of it, and it is worth saying out
loud: every other scanner is a function of the prompt, and this one is a
function of what a caller already decided. The `source` on each finding says
which, so an explanation names the scanner iriguchi cannot answer questions
about rather than implying it looked.

Not registered in `infrastructure/registry.py`, because a registry entry is
something you can select by name and this needs its findings passed in. It is
constructed by `iriguchi.route(findings=...)` and nowhere else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.sensitivity import Finding

__all__ = ["SuppliedScanner"]


@dataclass(frozen=True, slots=True)
class SuppliedScanner:
    """Findings from somewhere else, handed to the veto unchanged."""

    findings: tuple[Finding, ...] = ()

    @property
    def name(self) -> str:
        """Named for what it is rather than for what supplied it.

        A caller mixing sources would otherwise get one name covering several,
        and the per-finding `source` is where that detail belongs.
        """
        return "supplied"

    def scan(self, text: str) -> Sequence[Finding]:
        """Return what was handed over. `text` is deliberately unused.

        Not asserted against the text either -- a finding whose span runs past
        the end of the prompt is a caller error worth catching, and it is caught
        where spans are validated rather than here, so that this stays the one
        scanner with no opinion at all.
        """
        return self.findings
