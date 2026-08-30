"""Turning a decision into something a person reads.

Kept separate from `main.py` because this is the output the whole project is
judged on. A router that decides correctly and cannot say why is a router nobody
can audit, and `--explain` is where the auditing happens -- so it is written as a
function that returns a string, asserted against golden text, rather than a pile
of `print` calls nobody diffs.

**Ordering for reading is decided here, not in the domain.** `Reason.sort_key`
puts statements about the request before statements about a place in it, and
orders each group by source. That is a total order and not a useful one for a
person: a scanner failure matters more than a policy note, and the domain has no
notion of importance to sort by. Adding one would be a domain change for a
presentation concern, so the grouping lives here.

Nothing rendered here ever contains the prompt. A span is printed as offsets.
"""

from __future__ import annotations

from ...domain.decision import RoutingDecision
from ...domain.destination import Route

__all__ = ["render_decision"]

#: Sources, in the order a person needs them. Anything not named here follows,
#: alphabetically. A failure is first because it changes what every other line
#: means.
_SOURCE_ORDER = ("routing", "fallback", "mamori", "rules", "policy")

_HEADLINE = {
    Route.LOCAL: "LOCAL      nothing leaves this machine",
    Route.EXTERNAL: "EXTERNAL   via mamori, protected on the way out",
    Route.REFUSED: "REFUSED    nothing runs",
}


def _source_rank(source: str) -> tuple[int, str]:
    try:
        return (_SOURCE_ORDER.index(source), source)
    except ValueError:
        return (len(_SOURCE_ORDER), source)


def render_decision(decision: RoutingDecision, *, verbose: bool = False) -> str:
    """The whole account, for a person.

    Args:
        decision: What the router concluded.
        verbose: Print every reason. Without it, reasons are still all printed --
            there are rarely more than six -- but the findings and signals behind
            them are summarised rather than listed.
    """
    lines = [
        f"  route        {_HEADLINE[decision.route]}",
        f"  sensitivity  {decision.sensitivity.level.value}"
        f"{_count(len(decision.sensitivity.findings), 'finding')}",
        f"  complexity   {decision.complexity.band.value}"
        f"{_count(len(decision.complexity.signals), 'signal')}"
        f"{'  (two escalating markers)' if decision.complexity.short_circuited else ''}",
        "",
        "  reasons",
    ]

    for reason in sorted(decision.reasons, key=lambda r: (_source_rank(r.source), r.sort_key)):
        where = f"  {reason.span}" if reason.span is not None else ""
        lines.append(f"    {reason.rule:<34}{where}")
        lines.append(f"        {reason.detail}")

    lines.append("")
    if decision.removed:
        lines.append("  removed")
        for removal in decision.removed:
            lines.append(f"    {removal.destination.value:<12} {removal.reason.detail}")
    else:
        lines.append("  removed      nothing")

    lines.append("  sent         nothing")

    if verbose:
        lines.extend(_detail(decision))

    return "\n".join(lines)


def _detail(decision: RoutingDecision) -> list[str]:
    """Every finding and signal, for somebody debugging a rule.

    Findings print a span and never a value -- which is the point of the whole
    design and is worth being able to see for yourself.
    """
    lines = ["", "  findings"]
    if decision.sensitivity.findings:
        lines.extend(
            f"    {finding.rule:<34}  {finding.span}  [{finding.source}]"
            for finding in decision.sensitivity.findings
        )
    else:
        lines.append("    none")

    lines.extend(["", "  signals"])
    if decision.complexity.signals:
        lines.extend(
            f"    {signal.rule:<34}  weight {signal.weight:.2f}"
            f"{'  escalating' if signal.escalating else ''}"
            for signal in decision.complexity.signals
        )
    else:
        lines.append("    none")

    lines.append(f"    score {decision.complexity.score:.4f}")
    return lines


def _count(number: int, noun: str) -> str:
    if number == 0:
        return ""
    return f"   ({number} {noun}{'s' if number != 1 else ''})"
