"""A scanner that reports what it was handed.

Somebody who already runs Presidio, or a detector this project has never heard
of, has findings before iriguchi is involved. `SuppliedScanner` is how those
reach the veto without iriguchi importing anything to get them.

**Which findings it returns does not depend on the text.** Every other scanner
is a function of the prompt; this one is a function of what a caller already
decided. The `source` on each finding says which, so an explanation names the
scanner iriguchi cannot answer questions about rather than implying it looked.

**It does check that they are about this prompt.** That is not the same thing,
and the difference was a real defect: this file used to say a span running past
the end of the prompt "is caught where spans are validated rather than here",
and it was not caught anywhere. `Span` validates that an offset is not negative
and that the end is not before the start -- it has no text to compare against,
so the claim was unimplementable where it pointed.

A finding at 0-9999 on a two-character prompt reached the published document,
which states that spans are "in code points of the prompt as it was typed". A
consumer holding that document highlights nothing, or worse. So the one place
that has both the findings and the text checks them against each other, and a
pairing that cannot be true is refused.

Not registered in `infrastructure/registry.py`, because a registry entry is
something you can select by name and this needs its findings passed in. It is
constructed by `iriguchi.route(findings=...)` and nowhere else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.sensitivity import Finding
from ...errors import ScanError

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
        """Return what was handed over, once it can be true of this prompt.

        The text does not choose the findings and never will. It does bound
        them: a span is an offset into *this* prompt, so one that ends past the
        end of it is describing something else -- a caller who analysed a longer
        string, or got an offset wrong, and either way a document nobody can use.

        Raises:
            ScanError: naming every span that does not fit, the length it had to
                fit inside, and nothing from the text. Raised rather than
                clamped: a shortened span is a claim about where something was
                found, and inventing one is worse than refusing. The router turns
                this into the most restrictive route with a reason (ADR-0002), so
                a caller who gets it wrong loses the external destination rather
                than the decision.
        """
        limit = len(text)
        beyond = [finding for finding in self.findings if finding.span.end > limit]
        if beyond:
            listed = ", ".join(f"{f.rule} at {f.span}" for f in beyond)
            raise ScanError(
                f"{len(beyond)} supplied finding(s) run past the end of this prompt, "
                f"which is {limit} character(s) long: {listed}. A span is an offset "
                f"into the prompt it came with, so these are about some other text.",
                # Built from rule ids, spans and a length -- exactly what
                # ADR-0006 permits to travel, and nothing from the prompt. This
                # message is worth keeping: it names which supplied finding was
                # wrong, which is the whole diagnostic.
                quotable=True,
            )
        return self.findings
