"""Folding for matching, and the way back.

The whole module exists for one sentence in the port contract: offsets are into
the text as given. Every test here is about the map, not about the folding --
NFKC is the standard library's problem and is assumed to work.
"""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from iriguchi.domain.span import Span
from iriguchi.infrastructure.normalization import normalize

#: One character that folds to four. The reason `origin` cannot be a slice.
EXPANDING = "㍿"
#: `e` + U+0301: two characters that whole-string NFKC would compose into one,
#: and that this deliberately leaves alone. An escape rather than a literal --
#: the two forms look identical, and an editor that normalized this file would
#: silently turn the test into a tautology.
DECOMPOSED = "cafe\u0301"


class TestFolding:
    def test_full_width_becomes_ascii(self) -> None:
        assert normalize("ｔａｎａｋａ＠ｅｘ．ｃｏｍ").text == "tanaka@ex.com"

    def test_one_character_may_become_several(self) -> None:
        assert normalize(EXPANDING).text == "株式会社"

    def test_ordinary_text_is_left_alone(self) -> None:
        assert normalize("Contact me on Friday.").text == "Contact me on Friday."

    def test_it_does_not_compose_combining_marks(self) -> None:
        """Per character, not per string, and deliberately.

        Whole-string NFKC would turn these five characters into four and shift
        every offset after them. Folding one character at a time cannot, so the
        map stays one-to-one here -- at the cost that a pattern written against
        the composed `café` will not match this.
        """
        folded = normalize(DECOMPOSED)
        assert folded.text == DECOMPOSED
        assert len(folded.text) == len(DECOMPOSED)
        assert len(unicodedata.normalize("NFKC", DECOMPOSED)) < len(DECOMPOSED)


class TestMappingBack:
    def test_a_span_over_unchanged_text_is_itself(self) -> None:
        folded = normalize("hello world")
        assert folded.to_original(6, 11) == Span(6, 11)

    def test_a_span_after_an_expansion_is_pulled_back(self) -> None:
        """`㍿` is one character and folds to four, so everything after it sits
        three places further along in the folded text than in the original."""
        folded = normalize("㍿の請求書")
        assert folded.text == "株式会社の請求書"
        assert folded.to_original(4, 5) == Span(1, 2)

    def test_a_span_covering_an_expansion_covers_the_one_character(self) -> None:
        folded = normalize("㍿の請求書")
        assert folded.to_original(0, 4) == Span(0, 1)

    def test_a_partial_span_inside_an_expansion_still_names_its_source(self) -> None:
        """Half of `株式会社` is not half of `㍿`; there is no such thing.

        The map answers with the character it came from, which is the only
        honest answer and is why a span can come back shorter than it went in.
        """
        folded = normalize("㍿の請求書")
        assert folded.to_original(1, 3) == Span(0, 1)

    def test_an_empty_span_maps_to_a_position(self) -> None:
        folded = normalize("㍿の")
        assert folded.to_original(4, 4) == Span(1, 1)

    def test_an_empty_span_at_the_very_end_maps_to_the_end(self) -> None:
        """There is no origin entry past the last character, so the original
        length is the answer. Without this the map raises on a rule that fires
        at the end of the text."""
        folded = normalize("㍿")
        assert folded.to_original(4, 4) == Span(1, 1)

    @pytest.mark.parametrize(("start", "end"), [(-1, 2), (0, 99), (3, 1)])
    def test_a_span_outside_the_folded_text_is_refused(self, start: int, end: int) -> None:
        with pytest.raises(ValueError, match="outside the normalized text"):
            normalize("hello").to_original(start, end)


class TestTheMapHolds:
    """Fuzzed, because the interesting inputs are the ones nobody types."""

    @given(text=st.text(max_size=200))
    def test_every_folded_character_names_a_real_original_one(self, text: str) -> None:
        folded = normalize(text)
        assert len(folded.origin) == len(folded.text)
        assert all(0 <= index < len(text) for index in folded.origin)

    @given(text=st.text(max_size=200))
    def test_the_map_never_goes_backwards(self, text: str) -> None:
        """Folding is character by character, so origins are non-decreasing.

        Anything else would mean a span could map to a reversed range, and
        `Span` would refuse to be constructed -- a crash rather than a wrong
        answer, but still a crash.
        """
        folded = normalize(text)
        assert list(folded.origin) == sorted(folded.origin)

    @given(text=st.text(max_size=200))
    def test_every_span_maps_back_inside_the_original(self, text: str) -> None:
        """The port contract's clause, asserted against arbitrary input."""
        folded = normalize(text)
        for start in range(len(folded.text)):
            for end in range(start, min(start + 4, len(folded.text)) + 1):
                span = folded.to_original(start, end)
                assert 0 <= span.start <= span.end <= len(text)

    @given(text=st.text(max_size=100))
    def test_a_span_over_the_whole_thing_is_the_whole_thing(self, text: str) -> None:
        folded = normalize(text)
        span = folded.to_original(0, len(folded.text))
        assert span == Span(0, len(text)) if text else span == Span(0, 0)
