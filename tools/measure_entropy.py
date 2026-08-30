"""Measure Shannon entropy on tokens people actually paste.

    python tools/measure_entropy.py

The thresholds in `infrastructure/scanners/entropy.py` came from this table, and
they are only defensible while the table is reproducible. Run it after changing
a threshold, and put the result in `docs/measurements.md`.

The sample list is the argument. Two real-looking secrets, two things people
paste constantly that look random to a statistic, and two things that are long
and ordinary. Every value is invented -- a real key committed to a repository
that measures entropy would be a poor joke.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iriguchi.infrastructure.scanners.entropy import (
    classify_charset,
    looks_random,
    shannon_entropy,
)

#: `(what it is, the token)`. Grouped by what the answer ought to be.
SAMPLES: tuple[tuple[str, str], ...] = (
    # Should be found.
    ("an sk- style key", "sk-live-51H8xQeMwvJ4tRbN7cZpLdKf"),
    ("a base64 blob", "dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSBmb3IgdGVzdGluZw=="),
    ("a sha256 hex digest", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    # Should not be. All of these are pasted many times a day.
    ("a documentation URL", "https://docs.example.com/guides/getting-started"),
    ("a source file path", "src/iriguchi/infrastructure/scanners/fallback.py"),
    ("a long English word", "internationalization"),
    ("run-together English", "pleasereviewtheattacheddocument"),
    ("a repeated character", "a" * 30),
    # The two the entropy rule cannot decide, and does not try to.
    ("an AWS-style key id", "AKIAIOSFODNN7EXAMPLE"),
    ("an order number", "ORD-2026-0000148372"),
    ("a card-shaped digit run", "4111111111111111"),
    ("a uuid", "f47ac10b-58cc-4372-a567-0e02b2c3d479"),
)


def main() -> int:
    print(f"{'':26} {'len':>4} {'entropy':>8} {'charset':>8}  found?")
    print("-" * 62)
    for label, token in SAMPLES:
        verdict = "yes" if looks_random(token) else "no"
        print(
            f"{label:26} {len(token):>4} {shannon_entropy(token):>8.2f} "
            f"{classify_charset(token):>8}  {verdict}"
        )
    print()
    print("`found?` is the entropy rule alone. The vendor-prefix and digit-run")
    print("rules answer for the last three, which is the point: entropy is one")
    print("rule among several, not the detector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
