"""Generate routing cases with the adversaries planted where we know.

    python tools/generate_cases.py

Deterministic. No model runs here, and no random seed either: the same command
produces byte-identical cases, so a regression in the fixtures is a diff rather
than a mystery. tsumugi's generator is the template.

**The traps are the dataset.** A generated corpus of obvious prompts measures
nothing, because every router passes it -- tsumugi found this on its first eval
run, and ADR-0007 is that finding applied to routing. Every case below plants one
correct answer and at least one adversary against it, and the `PLAIN` cases exist
only as a baseline and are kept in a minority so they cannot flatter the numbers.

**Every case is verified by an oracle before it is written.** The oracle reads
only the labels -- never the router -- and checks the corpus is decidable, is not
all one class, covers every trap kind, and carries no real-looking personal data.
A generator that plants a trap wrongly produces a case that fails a *correct*
implementation, and that failure is expensive precisely because the instinct is
to go looking in the code.

Everything here is invented. These files ship inside the wheel.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "src" / "iriguchi" / "evaluation" / "data" / "generated.json"

LOG_LINE = "2026-08-30 12:00:0{n} INFO request {n} handled in 1{n}ms\n"
INVENTED_KEY = "sk-live-51H8xQeMwvJ4tRbN7cZpLdKf"
INVENTED_HEX = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@dataclass(frozen=True, slots=True)
class Draft:
    prompt: str
    sensitivity: str
    band: str
    trap: str
    note: str
    #: Appended to the trap name to make the id. Keeps ids stable when a case is
    #: added in the middle of a list.
    slug: str = field(default="")


def _log(lines: int) -> str:
    return "".join(LOG_LINE.format(n=i % 10) for i in range(lines))


DRAFTS: tuple[Draft, ...] = (
    # ---------------------------------------------------------------- plain
    Draft(
        "この記事を三行で要約してください。",
        "may_leave",
        "low",
        "plain",
        "",
        "summarise",
    ),
    Draft(
        "次の英文を日本語に訳してください。The meeting starts at nine.",
        "may_leave",
        "low",
        "plain",
        "",
        "translate",
    ),
    Draft(
        "この二つの設計案を比較して、それぞれの計算量を証明してください。",
        "may_leave",
        "high",
        "plain",
        "",
        "compare-and-prove",
    ),
    # ------------------------------------------------------- looks sensitive
    Draft(
        "https://docs.example.com/guides/getting-started の手順を要約して。",
        "may_leave",
        "low",
        "looks_sensitive",
        "A public documentation URL. Nothing here identifies anyone, and a "
        "router that holds this back has made the external route unreachable "
        "for ordinary work.",
        "public-url",
    ),
    Draft(
        "シャーロック・ホームズさんの推理方法を説明してください。",
        "may_leave",
        "low",
        "looks_sensitive",
        "A fictional character with an honorific attached. The fallback "
        "scanner's honorific rule fires; the stoplist cannot ever be complete "
        "enough to catch this, and the over-detection is the accepted cost.",
        "fictional-person",
    ),
    Draft(
        "注文番号 ORD-2026-0000148372 の配送状況を教えてください。",
        "may_leave",
        "low",
        "looks_sensitive",
        "An order number, which is eight or more digits and therefore "
        "indistinguishable from a card number without a checksum. The "
        "digit-run rule fires. This is the single largest source of "
        "over-caution in the fallback scanner and it is measured, not hidden.",
        "order-number",
    ),
    Draft(
        f"README のサンプル出力 {INVENTED_HEX} は何のハッシュですか。",
        "may_leave",
        "low",
        "looks_sensitive",
        "A sha256 digest quoted from documentation. High entropy, no secret. "
        "Entropy cannot tell a published hash from a private one.",
        "published-digest",
    ),
    # --------------------------------------------------------- hidden secret
    Draft(
        f"次の設定を英訳してください。\napi_key = {INVENTED_KEY}\nregion = tokyo",
        "must_stay_local",
        "low",
        "hidden_secret",
        "A trivial request wrapped around a credential. Routers that read the "
        "instruction and not the payload send this out. The key is invented.",
        "translate-config",
    ),
    Draft(
        "この文章の誤字を直してください。パスワードは correcthorsebattery です。",
        "must_stay_local",
        "low",
        "hidden_secret",
        "Proofreading, which is the canonical local-model task, with a "
        "credential in the body. Invented.",
        "proofread-password",
    ),
    # ---------------------------------------------------------- long and easy
    Draft(
        "次のログを要約してください。\n" + _log(120),
        "may_leave",
        "low",
        "long_and_easy",
        "Length is not difficulty. Every router that scores on input size "
        "sends this to the expensive model. The band label is `low` because "
        "the task is genuinely easy; the estimator's length rule will still "
        "fire, and the gap between the two is the point of the case.",
        "log-summary",
    ),
    Draft(
        "以下の箇条書きを整形してください。\n" + "- 項目です\n" * 200,
        "may_leave",
        "low",
        "long_and_easy",
        "Formatting a long list. Mechanical, and long.",
        "long-list",
    ),
    # ---------------------------------------------------------- short and hard
    Draft(
        "この補題を証明して。",
        "may_leave",
        "high",
        "short_and_hard",
        "Nine characters. No lexical or structural feature except the word "
        "`証明` distinguishes this from a greeting, which is why the "
        "escalating families exist.",
        "prove-lemma",
    ),
    Draft(
        "なぜこの設計は破綻するのか、根拠を挙げて説明して。",
        "may_leave",
        "high",
        "short_and_hard",
        "Short, and asks for reasoning with justification. Two escalating "
        "markers reach the top band by the short-circuit rather than by score.",
        "why-broken",
    ),
    # ------------------------------------------------------------ mixed script
    Draft(
        "この TypeScript の generics がなぜ推論に失敗するのか説明して。\n"
        "```ts\nfunction id<T>(x: T): T { return x }\nconst y = id<string>(1)\n```",
        "may_leave",
        "high",
        "mixed_script",
        "Japanese prose around an English code block. Mixed script, a code "
        "fence and a `なぜ` between them.",
        "typescript-generics",
    ),
    Draft(
        "下記の SQL を PostgreSQL 向けに書き直してください。\n"
        "```sql\nSELECT * FROM orders WHERE created_at > now() - interval '7 days'\n```",
        "may_leave",
        "moderate",
        "mixed_script",
        "Mixed script and a code fence, but no reasoning request. Included so "
        "that mixed script alone does not become a shortcut to the top band.",
        "sql-rewrite",
    ),
    # ------------------------------------------------------ outside the prose
    Draft(
        "このツール呼び出しの結果を要約して。\n"
        '{"tool": "fetch_config", "result": {"host": "internal.example.com", '
        f'"token": "{INVENTED_KEY}"}}}}',
        "must_stay_local",
        "low",
        "outside_the_prose",
        "The secret is in an attached payload, not the sentence. mamori's "
        "ADR-0030 found this shape: a tool call is text, and anything that "
        "reads only the instruction misses it entirely. Invented.",
        "tool-payload",
    ),
    Draft(
        "この JSON のスキーマを説明して。\n"
        '{"user": {"email": "kaori.tanaka@example.co.jp", "role": "admin"}}',
        "must_stay_local",
        "low",
        "outside_the_prose",
        "An address inside a structure rather than a sentence. Invented.",
        "json-email",
    ),
    # ---------------------------------------------------------- near duplicate
    Draft(
        "打ち合わせの日程を調整してください。",
        "may_leave",
        "low",
        "near_duplicate",
        "The safe half of a pair. Its twin adds one address and nothing else, "
        "so a router that decides these two the same way is not reading the "
        "text.",
        "schedule-clean",
    ),
    Draft(
        "打ち合わせの日程を調整してください。tanaka@example.com にも共有を。",
        "must_stay_local",
        "low",
        "near_duplicate",
        "The twin of `near_duplicate-schedule-clean`, one address longer. The "
        "reason on this decision has to name that address's span. Invented.",
        "schedule-with-address",
    ),
    Draft(
        "この二つの手法を比較して。",
        "may_leave",
        "moderate",
        "near_duplicate",
        "The safe half of a second pair, testing the other axis: identical "
        "request, and its twin carries a name.",
        "compare-clean",
    ),
    Draft(
        "この二つの手法を比較して。担当は佐藤さんです。",
        "must_stay_local",
        "moderate",
        "near_duplicate",
        "One honorific separates this from `near_duplicate-compare-clean`. Invented name.",
        "compare-with-name",
    ),
)


# --------------------------------------------------------------------------
# The oracle. Reads labels only, never the router.
# --------------------------------------------------------------------------

#: Domains a real address would use. `example.com` and friends are reserved by
#: RFC 2606 precisely so that invented data has somewhere to live.
REAL_DOMAINS = re.compile(r"@(?!example\.(?:com|org|net|co\.jp)\b)[\w.\-]+\.[a-z]{2,}")

VALID_SENSITIVITY = {"must_stay_local", "may_leave"}
VALID_BANDS = {"low", "moderate", "high"}
REQUIRED_TRAPS = {
    "looks_sensitive",
    "hidden_secret",
    "long_and_easy",
    "short_and_hard",
    "mixed_script",
    "outside_the_prose",
    "near_duplicate",
}


def check(cases: list[dict[str, object]]) -> list[str]:
    """Everything wrong with the corpus, as sentences. Empty is a pass."""
    problems: list[str] = []
    ids = [str(case["id"]) for case in cases]

    if len(set(ids)) != len(ids):
        problems.append("duplicate ids")

    for case in cases:
        cid, prompt = case["id"], str(case["prompt"])
        if case["sensitivity"] not in VALID_SENSITIVITY:
            problems.append(f"{cid}: unknown sensitivity {case['sensitivity']!r}")
        if case["band"] not in VALID_BANDS:
            problems.append(f"{cid}: unknown band {case['band']!r}")
        if not prompt.strip():
            problems.append(f"{cid}: empty prompt")
        if case["trap"] != "plain" and not str(case["note"]).strip():
            problems.append(f"{cid}: a trap with no note")
        if REAL_DOMAINS.search(prompt):
            problems.append(
                f"{cid}: an address outside the reserved example domains. These files "
                "ship inside the wheel; invent everything."
            )

    covered = {str(case["trap"]) for case in cases}
    missing = sorted(REQUIRED_TRAPS - covered)
    if missing:
        problems.append(f"no case covers {missing}")

    plain = sum(1 for case in cases if case["trap"] == "plain")
    if plain * 2 >= len(cases):
        problems.append(
            f"{plain} of {len(cases)} cases are plain. A corpus that is mostly "
            "baseline flatters every number in it."
        )

    classes = {str(case["sensitivity"]) for case in cases}
    if classes != VALID_SENSITIVITY:
        problems.append(
            "the corpus is all one sensitivity class. Negative cases are the only "
            "way over-detection gets measured."
        )

    return problems


def main() -> int:
    cases = [
        {
            "id": f"gen-{draft.trap.replace('_', '-')}-{draft.slug}",
            "prompt": draft.prompt,
            "sensitivity": draft.sensitivity,
            "band": draft.band,
            "trap": draft.trap,
            "note": draft.note,
        }
        for draft in DRAFTS
    ]
    cases.sort(key=lambda case: str(case["id"]))

    problems = check(cases)
    if problems:
        print("the oracle refused to write the corpus:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    # `newline=""` rather than the default. `Path.write_text` translates a
    # newline to the platform line ending, so this file would be CRLF on
    # Windows and LF on Linux -- and "the same command produces byte-identical
    # cases" would quietly mean "on the same operating system". The
    # determinism test found this.
    OUT.write_text(
        json.dumps(
            {
                "format_version": 1,
                "name": "generated",
                "source": "generated",
                # **A fact, written while it is still a fact.** Both hands are
                # this repository's: the prompts and their labels come out of
                # this file, and this file was written by whoever writes
                # iriguchi's rules, while looking at them.
                #
                # It is recorded now because after a model drafts a single case
                # `generated` means two things, and the twenty-one already here
                # could only be told apart by guessing. tsumugi reached that
                # position with twenty cases and could not honestly recover:
                # its value said `drafted` and nothing said by what.
                "provenance": {
                    "text": {
                        "produced_by": "tools/generate_cases.py",
                        "authored_by": "iriguchi",
                    },
                    "labels": {
                        "produced_by": "tools/generate_cases.py",
                        "authored_by": "iriguchi",
                    },
                },
                "description": (
                    "Routing cases with adversaries planted where we know (ADR-0007). "
                    "Generated by tools/generate_cases.py -- deterministic, no model "
                    "and no seed. Do not hand-edit; the next run discards the edit. "
                    "Every value is invented."
                ),
                "samples": cases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"wrote {len(cases)} cases to {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
