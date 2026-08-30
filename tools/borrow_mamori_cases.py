"""Turn mamori's labelled samples into iriguchi routing cases. Run once.

    python tools/borrow_mamori_cases.py --from ../mamori/src/mamori/evaluation/data

mamori's evaluation data is exactly the labelled sensitivity corpus this project
needs, and somebody already argued over every line of it. A sample carrying an
annotated entity is a prompt that must stay local; a negative sample is one that
may leave. That is a three-language corpus for the cost of this file.

**Why this is a tool and not a loader.** `evaluation/` may not import `mamori`
-- the `mamori-is-an-adapter` contract says so -- and finding an installed
package's data directory requires importing it. So the borrowing happens here,
offline, and what ships is the result. The corpus then works on a machine with
no mamori, which is the configuration most people are in.

**Every value in mamori's corpus is invented**, by its own rule, and a test
there refuses vendor-prefixed credentials outright. Nothing real is being copied.
Attribution travels with the file.

Deterministic: same input, byte-identical output. The band label is the one
judgement made here, and it is made by a rule rather than by hand, because a
hand-labelled band is a hand-labelled band nobody can reproduce.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "src" / "iriguchi" / "evaluation" / "data" / "borrowed-mamori.json"

#: `[[PERSON:田中太郎]]` -> the value, and the fact that there was an entity.
ANNOTATION = re.compile(r"\[\[([A-Z_]+):([^\]]*)\]\]")

#: Which of mamori's files to read. The `-core` sets are prose a person would
#: actually type. Its `-agent`, `-context` and `-docs` sets are other shapes
#: (tool payloads, retrieved context, documentation) and are left out of this
#: pass deliberately -- they deserve their own trap labels rather than being
#: swept in as ordinary prompts.
FILES = ("ja-core.json", "en-core.json", "zh-core.json")


def strip(annotated: str) -> tuple[str, bool]:
    """The prompt as a person would have typed it, and whether it had entities."""
    had_entities = bool(ANNOTATION.search(annotated))
    return ANNOTATION.sub(lambda m: m.group(2), annotated), had_entities


def band_for(prompt: str) -> str:
    """The one judgement, made by a rule so it is reproducible.

    mamori's samples are short business prose -- notes, greetings, a phone
    number in a sentence. None of it asks for reasoning, so the honest label is
    the lowest band, and the two exceptions are stated rather than eyeballed.

    This means the borrowed half of the corpus measures **the sensitivity axis
    only**. It says nothing about band accuracy, and the report's band figure
    should be read against the generated cases.
    """
    if len(prompt) >= 600:
        return "moderate"
    return "low"


def convert(path: Path) -> list[dict[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    locale = document.get("locale", path.stem)
    cases: list[dict[str, object]] = []

    for sample in document["samples"]:
        prompt, had_entities = strip(str(sample["annotated"]))
        note = str(sample.get("note", "")).strip()
        cases.append(
            {
                "id": f"mamori-{sample['id']}",
                "prompt": prompt,
                "sensitivity": "must_stay_local" if had_entities else "may_leave",
                "band": band_for(prompt),
                "trap": "plain",
                "note": (f"Borrowed from mamori {locale}-core ({sample['id']}). {note}".strip()),
            }
        )
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        help="mamori's src/mamori/evaluation/data directory",
    )
    args = parser.parse_args()

    cases: list[dict[str, object]] = []
    read: list[str] = []
    for name in FILES:
        path = args.source / name
        if not path.exists():
            print(f"skipping {name}: not found", file=sys.stderr)
            continue
        cases.extend(convert(path))
        read.append(name)

    if not cases:
        print(f"nothing found under {args.source}", file=sys.stderr)
        return 1

    cases.sort(key=lambda case: str(case["id"]))
    # `newline=""` rather than the default. `Path.write_text` translates a
    # newline to the platform line ending, so this file would be CRLF on
    # Windows and LF on Linux -- and "the same command produces byte-identical
    # cases" would quietly mean "on the same operating system". The
    # determinism test found this.
    OUT.write_text(
        json.dumps(
            {
                "format_version": 1,
                "name": "borrowed-mamori",
                "source": "borrowed:mamori",
                # **Two hands, and they are different ones.** mamori wrote the
                # prose; a rule in this file assigned the labels. Recorded as
                # `borrowed:mamori` alone, that was one word for two hands --
                # and the more flattering half was the one it named.
                #
                # This is the split tsumugi and akashi arrived at separately,
                # and the reason it matters here is that "text from elsewhere,
                # labels from us" is the only arrangement in this corpus that
                # measures anything other than its author's imagination.
                "provenance": {
                    "text": {
                        "produced_by": "mamori evaluation corpus",
                        "authored_by": "mamori",
                    },
                    "labels": {
                        "produced_by": "tools/borrow_mamori_cases.py",
                        "authored_by": "iriguchi",
                    },
                },
                "description": (
                    "Routing cases derived from mamori's labelled detection corpus "
                    f"({', '.join(read)}), Apache-2.0, by the same author. A sample "
                    "carrying an annotated entity becomes must_stay_local; a negative "
                    "sample becomes may_leave. Every value in mamori's corpus is "
                    "invented. Regenerate with tools/borrow_mamori_cases.py -- do not "
                    "hand-edit, because the next regeneration will discard the edit. "
                    "These cases measure the sensitivity axis; their band labels are "
                    "rule-assigned and say nothing about band accuracy."
                ),
                "samples": cases,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"wrote {len(cases)} cases from {', '.join(read)} to {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
