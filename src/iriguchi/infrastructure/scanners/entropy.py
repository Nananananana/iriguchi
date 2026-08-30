"""Shannon entropy, and the thresholds that make it usable.

Machine-generated secrets look random because they are; ordinary prose does not.
That is the whole idea, and on its own it produces a scanner nobody can live
with. The numbers in `docs/measurements.md` say why, and three of them decided
everything in this module:

- a live-looking `sk-` key scores **4.81**, and a base64 blob **4.68**;
- a URL path scores **4.14** and a file path **3.99** -- both things people paste
  constantly, both above any threshold that would catch a short key;
- `AKIAIOSFODNN7EXAMPLE` scores **3.68**, which is *below* the URL.

So entropy is not the detector. It is one rule among several, with a threshold
that clears the things people paste, and the short structured keys it cannot
reach are caught by their prefixes instead. detect-secrets reached the same
arrangement; the measurement here agrees with its default for the base64 charset
and disagrees about digits.
"""

from __future__ import annotations

import math
import re
from collections import Counter

__all__ = ["CharsetClass", "classify_charset", "shannon_entropy", "threshold_for"]

_HEX = re.compile(r"[0-9a-fA-F]+")
_DIGITS = re.compile(r"[0-9]+")


class CharsetClass:
    """Which alphabet a token appears to be drawn from.

    A plain class of string constants rather than an `Enum`: these are used as
    dictionary keys and in messages, and nothing here ever switches on them
    exhaustively enough for an enum to earn its import.
    """

    DIGITS = "digits"
    HEX = "hex"
    MIXED = "mixed"


#: Bits per character, above which a token of the right length is reported.
#:
#: `MIXED` is detect-secrets' default for the base64 alphabet, and the
#: measurement supports it: it sits above the URL path (4.14) and below the two
#: real secrets (4.68, 4.81). There is not much room in that gap, which is the
#: honest reason this rule needs the length floor as well.
#:
#: `HEX` is lower because it has to be. Hex tops out at 4.0 bits per character by
#: construction, and a real sha256 scores 3.67 -- a 4.5 threshold would never
#: fire on hex at all.
#:
#: There is no entry for `DIGITS`, deliberately. Ten symbols cap the entropy at
#: log2(10) = 3.32, so any threshold low enough to catch a numeric secret catches
#: every order number, invoice number and timestamp in the corpus. That
#: over-detection is real and belongs to the digit-run rule, which admits to it
#: in its own comment rather than hiding inside a statistic.
_THRESHOLDS: dict[str, float] = {
    CharsetClass.MIXED: 4.5,
    CharsetClass.HEX: 3.0,
}

#: Below these lengths the rule is dead weight rather than lenient. Shannon
#: entropy of an n-character string cannot exceed log2(n), so 4.5 bits is
#: unreachable under 23 characters and asking for it under 24 is asking for
#: nothing. Hex is longer still, because the things that are 32 or 64 hex
#: characters are hashes and keys, and the things that are 8 are colour codes.
_MIN_LENGTHS: dict[str, int] = {
    CharsetClass.MIXED: 24,
    CharsetClass.HEX: 32,
}


def shannon_entropy(token: str) -> float:
    """Bits per character, over the distribution the token actually shows.

    Over the observed characters rather than an assumed alphabet: `"aaaa"` is
    zero bits whatever charset it is drawn from, which is the answer that makes
    a repeated string stop looking like a secret.
    """
    if not token:
        return 0.0
    length = len(token)
    total = -sum((count / length) * math.log2(count / length) for count in Counter(token).values())
    # A single repeated character sums to exactly zero, and negating it gives
    # `-0.0`, which is correct and reads as a bug in every table it appears in.
    return total + 0.0


def classify_charset(token: str) -> str:
    """Which alphabet `token` looks drawn from.

    Order matters: every digit string is also a hex string, and calling one
    `HEX` would give it a threshold its alphabet cannot reach.
    """
    if _DIGITS.fullmatch(token):
        return CharsetClass.DIGITS
    if _HEX.fullmatch(token):
        return CharsetClass.HEX
    return CharsetClass.MIXED


def threshold_for(token: str) -> tuple[float, int] | None:
    """The entropy and length floors this token has to clear, or `None`.

    `None` means the entropy rule has no opinion about tokens of this kind --
    which today means digits, and is a statement about the alphabet rather than
    about this particular string.
    """
    charset = classify_charset(token)
    if charset not in _THRESHOLDS:
        return None
    return _THRESHOLDS[charset], _MIN_LENGTHS[charset]


def looks_random(token: str) -> bool:
    """Whether `token` clears both floors for its charset."""
    floors = threshold_for(token)
    if floors is None:
        return False
    entropy_floor, length_floor = floors
    return len(token) >= length_floor and shannon_entropy(token) >= entropy_floor
