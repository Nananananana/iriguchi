"""Entropy, its charset classes, and the arithmetic that pinned the thresholds.

Some of these are not really tests of the code -- they are the argument for the
constants, written where it will be run. `test_the_mixed_threshold_is_unreachable_`
`under_its_length_floor` is arithmetic about log2, and it exists so that somebody
lowering the length floor to 16 finds out immediately that they have turned the
rule off rather than loosened it.
"""

from __future__ import annotations

import math

import pytest

from iriguchi.infrastructure.scanners.entropy import (
    CharsetClass,
    classify_charset,
    looks_random,
    shannon_entropy,
    threshold_for,
)


class TestShannonEntropy:
    def test_the_empty_string_is_zero(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_one_repeated_character_is_zero_and_not_minus_zero(self) -> None:
        """`-0.0` is arithmetically correct and reads as a bug in every table."""
        assert shannon_entropy("a" * 30) == 0.0
        assert math.copysign(1.0, shannon_entropy("a" * 30)) > 0

    def test_two_equally_common_characters_are_one_bit(self) -> None:
        assert shannon_entropy("abab") == pytest.approx(1.0)

    def test_four_equally_common_characters_are_two_bits(self) -> None:
        assert shannon_entropy("abcd") == pytest.approx(2.0)

    def test_it_measures_the_observed_distribution_not_the_alphabet(self) -> None:
        """`aaaa` is zero bits whatever charset it was drawn from.

        The alternative -- assuming an alphabet from the character classes
        present -- would score a repeated string as if it were random, which is
        the one thing a person can look at and tell is not.
        """
        assert shannon_entropy("aaaa") == 0.0
        assert shannon_entropy("1111") == 0.0


class TestCharsetClasses:
    @pytest.mark.parametrize(
        ("token", "charset"),
        [
            ("1234567890", CharsetClass.DIGITS),
            ("deadbeef", CharsetClass.HEX),
            ("DEADBEEF", CharsetClass.HEX),
            ("sk-live-abc", CharsetClass.MIXED),
            ("hello world", CharsetClass.MIXED),
        ],
    )
    def test_it_classifies(self, token: str, charset: str) -> None:
        assert classify_charset(token) == charset

    def test_digits_are_checked_before_hex(self) -> None:
        """Order matters, and getting it wrong is silent.

        Every digit string is also a hex string. Classing `1234567890` as hex
        would hand it the 3.0 threshold, which its ten-symbol alphabet can very
        nearly reach -- so every long number would become a finding by a route
        that was supposed to have excluded them.
        """
        assert classify_charset("1234567890") == CharsetClass.DIGITS


class TestTheThresholdsAreReachable:
    """Arithmetic about the constants, not behaviour. It is here because a
    threshold that cannot be met is a rule that is off, and being off looks
    exactly like being lenient."""

    def test_digits_have_no_threshold_at_all(self) -> None:
        assert threshold_for("1234567890123456") is None
        assert not looks_random("4111111111111111")

    def test_the_digit_alphabet_could_not_have_had_a_useful_one(self) -> None:
        """log2(10) = 3.32 is the ceiling for any digit string, ever.

        `pytest.approx` rather than `<=`, because a perfectly uniform digit
        string hits the ceiling exactly and the summation lands one ULP above
        it. The claim is "cannot exceed", and at this precision that is a claim
        about the maths rather than about the float.
        """
        assert math.log2(10) == pytest.approx(3.3219, abs=1e-4)
        assert shannon_entropy("0123456789" * 4) == pytest.approx(math.log2(10))

    def test_the_mixed_threshold_is_reachable_at_its_length_floor(self) -> None:
        """4.5 bits needs at least 23 distinct characters. The floor is 24."""
        floors = threshold_for("sk-live-abcdefghijklmnop")
        assert floors is not None
        entropy_floor, length_floor = floors
        assert math.log2(length_floor) >= entropy_floor, (
            f"a {length_floor}-character token cannot exceed "
            f"{math.log2(length_floor):.2f} bits, so a floor of {entropy_floor} "
            "turns this rule off rather than loosening it"
        )

    def test_the_hex_threshold_is_below_what_hex_can_produce(self) -> None:
        """Hex tops out at 4.0 bits. A 4.5 threshold would never fire."""
        floors = threshold_for("a1b2c3d4" * 4)
        assert floors is not None
        assert floors[0] < math.log2(16)


class TestTheVerdict:
    @pytest.mark.parametrize(
        "token",
        [
            "sk-live-51H8xQeMwvJ4tRbN7cZpLdKf",
            "dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSBmb3IgdGVzdGluZw==",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ],
    )
    def test_it_fires_on_something_generated(self, token: str) -> None:
        assert looks_random(token)

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "https://docs.example.com/guides/getting-started",
            "src/iriguchi/infrastructure/scanners/fallback.py",
            "internationalization",
            "a" * 40,
            # Below the length floor, however random it looks.
            "Xq7Bz",
            # Short structured keys: the hole the vendor-prefix rule fills.
            "AKIAIOSFODNN7EXAMPLE",
        ],
    )
    def test_it_stays_quiet_on_something_typed(self, token: str) -> None:
        assert not looks_random(token)

    def test_a_hex_digest_fires_where_the_mixed_threshold_would_not(self) -> None:
        """The reason hex has its own number: 3.67 bits, and 4.5 is impossible."""
        digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert classify_charset(digest) == CharsetClass.HEX
        assert shannon_entropy(digest) < 4.5
        assert looks_random(digest)
