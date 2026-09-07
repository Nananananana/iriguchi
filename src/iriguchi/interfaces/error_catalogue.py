"""Every named failure iriguchi can print, and the ones that are not failures.

Sora asked for this (`iriguchi-work/05_sora_errors_requirement.md`, R-E1) and
said outright that they copied the shape from `rules --json`. They fold repeated
failures into one line of `incidents.jsonl` keyed on the name before the colon
in stderr, and they keep **no values** — the name only, the sentence discarded,
because stderr can quote what was handed to it.

Three things were measured before this table was written, and two of them were
wrong on iriguchi's side.

## What Sora's fold key actually was

Every `IriguchiError` reached stderr as `iriguchi: <message>`. So the name before
the colon was `iriguchi`, for all of them:

    iriguchi: the scanner 'mamori' is registered and cannot be used ...
    iriguchi: --findings could not read '/nope/nothing.json' ...
    iriguchi: --findings is not a UTF-8 JSON document ...
    iriguchi: ['IRIGUCHI_LOCAL_URL', 'IRIGUCHI_LOCAL_MODEL'] is not set ...

Four unrelated failures folding into one incident row called `iriguchi`, which
is the same amount of information as a counter. R-E2 was filed as *a request,
not a requirement*; it was in fact the more urgent half, and the first line is
`Kind: ...` now.

## The exit code said the opposite of what happened

iriguchi publishes `0` decided, `2` refused, `1` broken, and Sora maps `2` to
`refused` and deliberately does not colour it as an error — a refusal is a
decision this router is proud of.

argparse exits `2` for a mistyped flag. So `iriguchi --nosuchflag route "..."`
arrived at Sora as **a routing refusal**: no decision document, nothing on
stdout, and a screen saying the prompt was refused. A false statement about a
policy decision, produced by a typo. Usage errors exit `1` now, which is what
iriguchi's own published sentence already said they should.

## What is deliberately not in here

The `RoutingError` family — `ScanError`, `EstimationError`, `JudgementError`.
They are raised, and they never reach a person as failures: ADR-0002 turns each
into the most restrictive route available with a reason naming what broke. They
appear in `rules --json` — as `routing.scanner-failed`,
`routing.estimator-failed` and **`cascade.judge-failed`**, which is not the tidy
set of three this file assumed on its first draft. The judge's sits on the
cascade's prefix because the cascade is where a broken judge changes anything.
`NOT_A_FAILURE` below carries the real identifiers, and a test drives them
through `rules --json` so this cross-reference cannot point at a rule that does
not exist — which the first draft did. Sora guessed the substance of this
correctly before asking.

`open_namespaces` is empty, and that is a claim rather than an omission. Every
kind here is one of iriguchi's own class names; a foreign exception never
reaches the top-level handler, because the adapters wrap what they catch. The
one that escaped — `OSError` from an unreadable `--findings` file — was found by
running the command and is wrapped now.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["CONTRACT", "ERRORS", "NOT_A_FAILURE", "OPEN_NAMESPACES", "as_document"]

CONTRACT = "iriguchi.errors/1-draft"

#: kind, exit code, outcome, retryable, English, Japanese.
#:
#: **`retryable` is not a forecast.** Sora first asked whether asking again could
#: succeed; that is a question about *possibility*, and the one a consumer needs
#: answered is about *permission*. They adopted the narrower reading and wrote it
#: better than it had been put here:
#:
#:     may the same request be issued again, unchanged — and a failure where
#:     re-issuing is itself a new event (it leaves the machine, it is billed, it
#:     leaves a trace) is `false` even when it could succeed
#:
#: mamori reached the same sentence independently, which is the reason to trust
#: it rather than a coincidence to note.
#:
#: **Applying it here moved an entry.** `ModelError` was `true`, on the reasoning
#: that a model which timed out might answer next time. It is raised by
#: `Asker._outward` *after* `external.answer()` has returned — which is the one
#: line in this package that sends — so on that path re-issuing sends the prompt
#: again. One kind spans the local path and the outbound one, and the answer for
#: a kind that spans them is the restrictive one: ADR-0002's rule, applied to a
#: document rather than to a route.
#:
#: The cost is real and worth naming. A local model that was simply not running
#: is safely retryable and now says otherwise. Recovering that means **splitting
#: the kind**, so the outbound failure has a name of its own — a change to the
#: exception tree rather than to this table, and nobody has needed it yet.
#:
#: So every entry is `false`, and that is a statement rather than an oversight.
ERRORS: tuple[tuple[str, int, str, bool, str, str], ...] = (
    (
        "ConfigurationError",
        1,
        "failed",
        False,
        "A setting, flag or input document was missing, malformed, or not one "
        "iriguchi accepts. Unknown keys are refused rather than ignored.",
        "設定・引数・入力文書が、欠けているか、壊れているか、"
        "iriguchi が受け付けないものだった。知らないキーは無視せず拒否する。",
    ),
    (
        "EscalationRefusedError",
        1,
        "refused",
        False,
        "A prompt that was allowed to leave will not be sent after all, because "
        "the protection the route depends on could not be arranged. The prompt "
        "stays where it is; nothing is sent less protected instead.",
        "外に出してよいと決まったプロンプトを、結局送らなかった。"
        "経路が前提にしている保護を用意できなかったため。"
        "プロンプトはその場に留まる。保護を弱めて送ることはしない。",
    ),
    (
        "ModelError",
        1,
        "unavailable",
        False,
        "A model could not answer -- unreachable, too slow for its timeout, or "
        "answering in a shape this build does not understand. The route was "
        "already decided and is not in doubt. **Not retryable, and the local "
        "case is the reason this is not obvious**: on the outbound path the "
        "send has already happened when this is raised, so re-issuing the same "
        "request sends the prompt a second time. One kind spans both paths, and "
        "the answer for a kind that spans them is the restrictive one.",
        "モデルが答えられなかった。到達できないか、時間切れか、"
        "この版が解釈できない形で返ってきたか。経路は既に決まっており、疑われていない。"
        "**再試行不可。ローカルの場合を考えると自明でないが**、外向きの経路では"
        "これが上がる時点で送信は既に済んでいるので、同じ要求を出し直すと"
        "プロンプトがもう一度外に出る。1 つの kind が両方の経路にまたがっており、"
        "またがる kind の答えは制限の強いほうである。",
    ),
    (
        "InteropError",
        1,
        "failed",
        False,
        "A foreign analyzer's result could not be read -- a missing field, an "
        "offset that is not an integer, or a span that runs backwards or before "
        "the start of the prompt. It is refused rather than skipped, because a "
        "batch of findings quietly one short is a prompt scanned less than the "
        "caller believes.",
        "他所の検出器の結果が読めなかった。欄が欠けているか、"
        "オフセットが整数でないか、範囲が逆向きか先頭より前にある。"
        "飛ばさずに拒否する。黙って 1 件少ない finding の束は、"
        "呼び出し側が思っているより浅く走査されたプロンプトだからである。",
    ),
    (
        "RestorationError",
        1,
        "failed",
        False,
        "An answer came back and could not be fully restored. Reported rather "
        "than returned half-restored, because a partly restored answer reads as "
        "complete and quotes a placeholder as though it were a fact.",
        "答えが返ってきたが、元に戻しきれなかった。"
        "途中まで戻したものを返さずに報告する。"
        "半分戻った答えは完全な答えに見え、置き換え記号を事実として引用してしまうため。",
    ),
)

#: Prefixes whose second half comes from somebody else's vocabulary.
#:
#: Empty, and it is a claim: every kind above is one of iriguchi's own class
#: names, and an adapter that catches a foreign exception wraps it before it can
#: reach the top-level handler.
OPEN_NAMESPACES: tuple[tuple[str, str, str], ...] = ()

#: Raised, and never printed as a failure. Declared so the absence is a stated
#: fact rather than a gap a consumer has to notice.
#:
#: kind, where it goes instead, English, Japanese.
NOT_A_FAILURE: tuple[tuple[str, str, str, str], ...] = (
    (
        "ScanError",
        "routing.scanner-failed",
        "A sensitivity scanner broke. ADR-0002 turns this into the most "
        "restrictive route available with a reason naming the scanner, so it "
        "reaches you as a decision and never as a failure.",
        "検出器が壊れた。ADR-0002 により、"
        "利用できる中で最も制限の強い経路と、壊れた検出器を名指しする理由になる。"
        "失敗ではなく決定として届く。",
    ),
    (
        "EstimationError",
        "routing.estimator-failed",
        "A complexity estimator broke. No signals is already the lowest band, "
        "which routes local, so the safe answer is the default here -- reported "
        "anyway, because a decision that quietly lost an axis looks exactly "
        "like one where that axis had no opinion.",
        "複雑度の推定器が壊れた。信号なしは既に最も低い帯で、ローカルに向かうため、"
        "安全な答えがそのまま既定になる。それでも報告する。"
        "軸を黙って失った決定は、その軸に意見がなかった決定と見分けがつかないため。",
    ),
    (
        "JudgementError",
        "cascade.judge-failed",
        "An answer judge broke. A broken judge cannot cause a prompt to leave: "
        "escalation is gated on the original decision having permitted it, and "
        "that decision was made before any of this ran.",
        "答えの判定器が壊れた。壊れた判定器がプロンプトを外に出すことはない。"
        "エスカレーションは元の決定が許可していることを条件にしており、"
        "その決定はこれらが動く前に済んでいる。",
    ),
)


def as_document(version: str) -> Mapping[str, Any]:
    """The catalogue as `iriguchi.errors/1-draft`.

    `version` is passed in rather than read here, for the reason
    `interfaces.rules.as_document` states: a table that reaches for the package
    to learn its own version is a table with a dependency.
    """
    errors: Sequence[Mapping[str, Any]] = [
        {
            "kind": kind,
            "exit_code": exit_code,
            "outcome": outcome,
            "retryable": retryable,
            "detail": detail,
            "detail_ja": japanese,
        }
        for kind, exit_code, outcome, retryable, detail, japanese in ERRORS
    ]
    return {
        "contract": CONTRACT,
        "by": f"iriguchi/{version}",
        "errors": errors,
        "open_namespaces": [
            {"prefix": prefix, "detail": detail, "detail_ja": japanese}
            for prefix, detail, japanese in OPEN_NAMESPACES
        ],
        "not_a_failure": [
            {"kind": kind, "reported_as": rule, "detail": detail, "detail_ja": japanese}
            for kind, rule, detail, japanese in NOT_A_FAILURE
        ],
    }
