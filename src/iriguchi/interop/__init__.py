"""Speaking somebody else's vocabulary without importing them.

The most common thing a person already has, when they arrive here, is a
**Presidio analyzer**. They have tuned recognizers, they trust the output, and
being told to throw it away and use a built-in scanner that misses 61.7% of
must-stay-local cases is not an offer.

So: bring your results, keep your analyzer.

    >>> from iriguchi import route
    >>> from iriguchi.interop import findings_from_presidio
    >>> results = analyzer.analyze(text, language="en")   # yours, unchanged
    >>> route(text, findings=findings_from_presidio(results), local=True, external=True)

`iriguchi` does not import Presidio, does not depend on it, and does not need it
installed to run any of this. mamori arrived at the same three rules from the
other side and they are worth stating rather than re-deriving:

**Do not inherit their types.** A same-shaped `dataclass` keeps `.entity_type`,
`.start`, `.end` and `.score` working for code that reads them, and keeps *"you
can try this without installing anything"* true. ADR-0009 already says this
about tsumugi: borrow the vocabulary, not the dependency.

**Accept dicts as readily as objects.** A fixture loaded from JSON is the
commonest thing anybody actually holds, and demanding a class puts an install
back in the way.

**Swallow keyword arguments you do not implement.** The line a migrating user is
least able to change is the constructor they already wrote.

## And the one that is not about convenience

Presidio's `anonymize` writes `<PERSON>` and drops the original. mamori writes
`<PERSON_001>` and can put it back, and **returning `<PERSON>` to look more
familiar would silently discard the reason the library exists.**

iriguchi's version of that trap is a number. A `RecognizerResult` carries a
`score` and it is a confidence. iriguchi's findings carry none — deliberately,
because *a confidence becomes a threshold and a threshold is a score somebody
tunes until the leak rate looks acceptable*. So `to_presidio` fills `score` with
`1.0` and says why, and `findings_from_presidio` **throws an incoming score
away** rather than storing a number iriguchi would then have to pretend to mean.

Losing that information is the honest outcome: a veto does not have degrees.
"""

from __future__ import annotations

from .presidio import (
    RecognizerResult,
    findings_from_presidio,
    to_presidio,
)

__all__ = [
    "RecognizerResult",
    "findings_from_presidio",
    "to_presidio",
]
