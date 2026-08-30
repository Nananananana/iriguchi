"""Where in a prompt a rule fired.

A span, and never the characters inside it. Everything in this package that
wants to point at part of a prompt points with one of these, which is how a
routing decision can be fully explained without any of it being quotable
(ADR-0006).

Offsets are into the text as the caller supplied it. This package does no
normalization: an adapter that scans normalized text is responsible for mapping
back before it reports, because a span that means something different depending
on who is reading it is worse than no span at all.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Span"]


@dataclass(frozen=True, slots=True, order=True)
class Span:
    """A half-open character range, ``[start, end)``.

    Ordered, and the ordering is total. Reason lists are sorted by span, and a
    partial sort key would let two runs of the same code produce two different
    orderings -- which AGENTS.md forbids and a test asserts.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"span start must not be negative, got {self.start}")
        if self.end < self.start:
            raise ValueError(f"span end {self.end} is before its start {self.start}")

    @property
    def length(self) -> int:
        """Characters covered. Zero is legitimate: a rule may fire on a position.

        An empty prompt, a missing required section, a boundary between two
        parts -- each is something a rule might have an opinion about, and none
        of them covers a character.
        """
        return self.end - self.start

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"
