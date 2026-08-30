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
    origin: tuple[int, ...] = field(repr=False)
    #: How long the original was. Needed to close a span that reaches the end.
    original_length: int = 0

    def to_original(self, start: int, end: int) -> Span:
        """Map a half-open span in `text` back to one in the original.

        The end is the awkward half. `origin` names where each normalized
        character *started*, so the end of a span is one past the origin of its
        last character -- not the origin of the character after it, which may be
        several characters further on when the last one folded to three.
        """
        if not 0 <= start <= end <= len(self.text):
            raise ValueError(f"span {start}-{end} is outside the normalized text")
        if start == end:
            at = self.origin[start] if start < len(self.origin) else self.original_length
            return Span(at, at)
        return Span(self.origin[start], self.origin[end - 1] + 1)


def normalize(text: str) -> NormalizedText:
    """Fold `text` for matching, recording where every character came from."""
    folded: list[str] = []
    origin: list[int] = []
    for index, character in enumerate(text):
        replacement = unicodedata.normalize("NFKC", character)
        folded.append(replacement)
        origin.extend([index] * len(replacement))
    return NormalizedText(text="".join(folded), origin=tuple(origin), original_length=len(text))
