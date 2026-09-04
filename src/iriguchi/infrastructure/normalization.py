"""Normalize for matching, and keep the way back.

A scanner has to see `ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ` as an email address.
Missing it means the prompt goes *out*, which is the unsafe direction, so
matching against raw text is not an option.

But `SensitivityScanner` promises offsets into the text as given, and a span into
the normalized string points at the wrong characters as soon as normalization
changes a length. So normalization here produces both the folded text and a map
from every normalized index back to the original one. mamori's ADR-0004, same
reasoning and the same shape.

**Per character, not per string, and the difference is deliberate.** Folding each
character on its own means `e` + U+0301 stays two characters rather than
composing to `é`, so those offsets stay one-to-one. The cost is that a pattern
written against the composed form will not match the decomposed one -- and that
is the right trade here, because this scanner matches ASCII-shaped things
(addresses, keys, digit runs) where the full-width fold is what matters and
accent composition is not.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from ..domain.span import Span

__all__ = ["NormalizedText", "normalize"]


@dataclass(frozen=True, slots=True)
class NormalizedText:
    """Folded text, and the way back to the original offsets."""

    #: NFKC-folded, one character at a time.
    text: str
    #: For each index in `text`, the index in the original it came from.
    #: One entry per normalized character; a character that folded to three
    #: contributes three entries all naming the same original index.
    #:
    #: **`None` is the identity map**, and it is the common case: text that is
    #: already NFKC-normal folds to itself, so index `i` came from index `i`.
    #: Storing a tuple to say that costs one machine word per character of every
    #: prompt, to hold `0, 1, 2, 3, ...`.
    origin: tuple[int, ...] | None = field(default=None, repr=False)
    #: How long the original was. Needed to close a span that reaches the end.
    original_length: int = 0

    @property
    def origins(self) -> tuple[int, ...]:
        """The map, materialised.

        `origin` is `None` when normalization changed nothing, because storing
        `0, 1, 2, ...` costs a machine word per character of every prompt to say
        so. Anything that wants the map itself rather than a span translation
        should ask here, so the representation stays an implementation detail --
        two tests were reading the field directly and broke when it learned to
        be `None`.
        """
        return tuple(range(len(self.text))) if self.origin is None else self.origin

    def to_original(self, start: int, end: int) -> Span:
        """Map a half-open span in `text` back to one in the original.

        The end is the awkward half. `origin` names where each normalized
        character *started*, so the end of a span is one past the origin of its
        last character -- not the origin of the character after it, which may be
        several characters further on when the last one folded to three.
        """
        if not 0 <= start <= end <= len(self.text):
            raise ValueError(f"span {start}-{end} is outside the normalized text")
        if self.origin is None:
            return Span(start, end)
        if start == end:
            at = self.origin[start] if start < len(self.origin) else self.original_length
            return Span(at, at)
        return Span(self.origin[start], self.origin[end - 1] + 1)


def normalize(text: str) -> NormalizedText:
    """Fold `text` for matching, recording where every character came from.

    **The fast path is the common one.** Text that is already NFKC-normal folds
    to itself, and the loop below then spends one `unicodedata.normalize` call
    and two list appends per character to rebuild the string it was given and an
    offset map that is `range(len(text))`. Profiling a 6135-character prompt put
    this function at **53% of the whole estimate**, on 6135 normalize calls that
    each returned their own argument.

    `is_normalized` answers the question in C, over the whole string, without
    allocating. When it says yes, the fold is the identity and so is the map.

    That shortcut is sound because a character with a compatibility
    decomposition decomposes wherever it appears -- so a string containing one
    is not NFKC-normal, and takes the slow path. The reverse direction is the
    interesting one and is asserted by a property test rather than by this
    paragraph: over generated text, whenever `is_normalized` is true, the
    per-character fold returns the input unchanged.
    """
    if unicodedata.is_normalized("NFKC", text):
        return NormalizedText(text=text, origin=None, original_length=len(text))

    folded: list[str] = []
    origin: list[int] = []
    for index, character in enumerate(text):
        replacement = unicodedata.normalize("NFKC", character)
        folded.append(replacement)
        origin.extend([index] * len(replacement))
    return NormalizedText(text="".join(folded), origin=tuple(origin), original_length=len(text))
