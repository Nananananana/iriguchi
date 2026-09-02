"""Printing content to a console that cannot represent it.

**A decision's explanation cannot hit this**, and the reason is a rule written
for something else: *messages carry rule ids, spans and types, never a matched
value*. Reasons, findings and signals are ASCII by construction, so the privacy
rule keeps the encoding hazard out of them as a side effect.

**That exemption covers the explanation and not the command.** An earlier
version of this docstring said `route --explain` could not hit the bug at all,
which is false: on an outbound route it prints `would leave`, and that is the
protected text — verbatim when nothing needed protecting. The test written to
support the claim set `IRIGUCHI_LOCAL=1` and never took that branch.

So there are three lines that carry characters the person typed, not two: `ask`
prints the model's answer, `ask --dry-run` prints the protected text, and
`route --explain` prints it too on an outbound route. On a Japanese console —
`cp932`, which is what a default Windows terminal here uses — an `é`, an em dash
or a bullet raises `UnicodeEncodeError` and the command dies.

akashi found the same class in themselves and named the reason it survived
construction: *every command run while building was prefixed with
`PYTHONUTF8=1`, exactly the setting the reader does not have.* A source scan
cannot find iriguchi's version of it either, because **the characters come from
the prompt and not from any string in this repository.**

## Why the replacement is announced rather than silent

`errors="replace"` alone would be worse than the crash. `would leave` exists to
show **what would actually be sent**, and a `?` where a character was makes the
display disagree with the payload — quietly, in the one command whose whole
purpose is to let a person check before anything leaves. So the substitution is
stated, counted, and paired with the fact that the payload is untouched.

Printing nothing is not an option either: the answer or the protected text is
the thing the person asked to see.
"""

from __future__ import annotations

from typing import TextIO

__all__ = ["print_content"]

#: What a stream that has no encoding is treated as. `io.StringIO` has none, and
#: neither does a redirected pipe on some platforms; assuming UTF-8 there is the
#: same assumption Python itself makes and keeps tests honest about the console
#: they are actually simulating.
_ASSUMED = "utf-8"


def _unprintable(text: str, encoding: str) -> list[str]:
    """The distinct characters this console cannot represent, in order.

    Per character rather than by encoding the whole string, because the useful
    report is *which* characters and how many, and a single `UnicodeEncodeError`
    names only the first.
    """
    missing: list[str] = []
    for character in text:
        if character in missing:
            continue
        try:
            character.encode(encoding)
        except UnicodeEncodeError:
            missing.append(character)
    return missing


def print_content(text: str, out: TextIO, *, indent: str = "") -> None:
    """Print text that came from outside, on whatever console this is.

    Falls back to a replaced rendering with a stated count when the console
    cannot carry the characters. **The payload is never altered** — this is a
    display concern and the note says so, because the alternative is a person
    reading a `?` and believing that is what would be sent.
    """
    encoding = getattr(out, "encoding", None) or _ASSUMED
    missing = _unprintable(text, encoding)
    if not missing:
        for line in text.splitlines() or [""]:
            print(f"{indent}{line}", file=out)
        return

    shown = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    for line in shown.splitlines() or [""]:
        print(f"{indent}{line}", file=out)
    listed = " ".join(f"U+{ord(character):04X}" for character in missing[:8])
    more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
    print(
        f"{indent}[{len(missing)} character(s) this console ({encoding}) cannot show, "
        f"replaced above: {listed}{more}. **The text itself is unchanged** -- this is "
        f"what your terminal can draw, not what would be sent.]",
        file=out,
    )
