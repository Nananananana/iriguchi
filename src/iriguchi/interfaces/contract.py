"""A decision somebody else's program can read.

Until now iriguchi printed for a person and nothing else. It consumes
`mamori.protection-scope/1`, it will read `tsumugi.context-package/1`, and it
**produced nothing** — the one repository in the family with arrows going in and
none coming out.

`iriguchi.routing-decision/1` is the arrow out. `iriguchi route --json` writes
it, `iriguchi schema` prints the schema, and both are what a 2026 command-line
tool is expected to have: a machine-readable mode that pipes into `jq`, and a
way to fetch the shape without reading the source.

## What makes it safe to publish, given ADR-0012

ADR-0012 refuses to keep a decision, on the grounds that **a decision inherits
the classification of the prompt it describes**. Emitting one as JSON looks like
the opposite, and is not, because of what the document contains:

    rule ids, source names, details   written by iriguchi, not by the prompt
    spans                            offsets into a prompt the reader lacks
    bands, scores, weights            arithmetic

**No string here is derived from the text.** A document saying
`fallback.email at 12-19` next to a prompt nobody has is not that prompt. The
same rule that makes `route --explain` printable is what makes this publishable,
and it is the rule ADR-0006 already states: *messages carry rule ids, spans and
types, never a matched value.*

That is not a promise made in prose. `tests/test_the_claims_with_no_mechanism.py`
sweeps the output of every command for planted values, and this document is in
the sweep.

## Offsets are code points, and the schema says so

Not bytes. An offset into UTF-8 bytes and an offset into characters disagree on
every Japanese prompt, and a consumer that guesses wrong highlights the wrong
words — silently, and worse the more the text needed protecting.
"""

from __future__ import annotations

import importlib.resources
import json
from typing import Any

from .. import __version__
from ..domain.complexity import Complexity, Thresholds
from ..domain.decision import RoutingDecision
from ..domain.reason import Reason
from ..domain.sensitivity import Sensitivity
from ..domain.span import Span

__all__ = ["CONTRACT", "SCHEMA_RESOURCE", "as_document", "schema"]

#: The identifier a consumer checks first, and the field that carries the state.
#: akashi found the cost of putting that on the second field a reader looks at;
#: mamori found the cost of putting it on a summary rather than an identifier.
#: This is the first key in the document and the only thing a consumer needs to
#: read before deciding whether it understands the rest.
CONTRACT = "iriguchi.routing-decision/1"

SCHEMA_RESOURCE = "schemas/routing-decision-1.json"


def schema() -> dict[str, Any]:
    """The published schema, read from the wheel.

    From the installed package rather than the repository, so `iriguchi schema`
    prints what a consumer actually has. A schema that only exists next to the
    source is a schema nobody downstream can check against.
    """
    resource = importlib.resources.files("iriguchi").joinpath(SCHEMA_RESOURCE)
    return json.loads(resource.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _span(span: Span | None) -> dict[str, int] | None:
    return None if span is None else {"start": span.start, "end": span.end}


def _with_span(base: dict[str, Any], span: Span | None) -> dict[str, Any]:
    """Omit `span` rather than emitting `null`.

    The schema marks it optional, and absent reads as *this is about the request
    as a whole* while `null` reads as *there was a span and it was nothing*.
    Those are different claims, and mamori's `reversible` taught this repository
    what the second one costs.
    """
    found = _span(span)
    return base if found is None else {**base, "span": found}


def _reason(reason: Reason) -> dict[str, Any]:
    return _with_span(
        {"rule": reason.rule, "source": reason.source, "detail": reason.detail}, reason.span
    )


def _sensitivity(sensitivity: Sensitivity) -> dict[str, Any]:
    return {
        "level": sensitivity.level.value,
        "findings": [
            {"rule": f.rule, "source": f.source, "span": _span(f.span)}
            for f in sorted(sensitivity.findings, key=lambda f: (f.span.start, f.rule))
        ],
    }


def _complexity(complexity: Complexity) -> dict[str, Any]:
    return {
        "band": complexity.band.value,
        "score": complexity.score,
        "short_circuited": complexity.short_circuited,
        "signals": [
            _with_span(
                {
                    "rule": s.rule,
                    "kind": s.kind.value,
                    "weight": s.weight,
                    "escalating": s.escalating,
                },
                s.span,
            )
            for s in complexity.signals
        ],
    }


def as_document(decision: RoutingDecision, thresholds: Thresholds | None = None) -> dict[str, Any]:
    """One decision, as `iriguchi.routing-decision/1`.

    `thresholds` is optional and **absent means not recorded**, not that the
    defaults applied. mamori draws the same distinction for `recall` and the
    reason is the one this family keeps relearning: a field that reads as a
    default when it is really a silence is a field that lies quietly.

    Ordering is stable -- reasons by the same key the renderer uses, findings by
    offset, signals as the domain sorted them -- so two runs on one prompt
    produce byte-identical output and a diff between two documents is a
    difference in the decision.
    """
    document: dict[str, Any] = {
        "contract": CONTRACT,
        "by": f"iriguchi/{__version__}",
        "route": decision.route.value,
        "sensitivity": _sensitivity(decision.sensitivity),
        "complexity": _complexity(decision.complexity),
        "reasons": [_reason(r) for r in sorted(decision.reasons, key=lambda r: r.sort_key)],
        "removed": [
            {"destination": r.destination.value, "reason": _reason(r.reason)}
            for r in decision.removed
        ],
    }
    if thresholds is not None:
        document["thresholds"] = {
            "moderate_at": thresholds.moderate_at,
            "high_at": thresholds.high_at,
            "short_circuit_at": thresholds.short_circuit_at,
        }
    return document
