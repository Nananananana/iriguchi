"""Every rule identifier iriguchi can put in a decision, and the ones it cannot.

Sora asked for this (`iriguchi-work/05_sora_round2.md`, R7) with a sharp
acceptance condition: *no rule appears in a decision that is not in this list*.
They key three languages of translation off `rule`, and the failure they want to
prevent is iriguchi adding a rule and their screen showing `policy.something-new`
in raw ASCII to a person reading Japanese.

**The condition cannot hold as stated, and saying so is most of the value here.**

`presidio.person` and `mamori.email` are built as `f"{source}.{entity_type}"`
from whatever a foreign detector returns. Which identifiers exist depends on
which recognisers that detector has installed and how it is configured —
iriguchi never sees the list and could not enumerate it without importing the
thing it refuses to import. A flat list would be silently incomplete, which is
worse than a list that says where its edges are.

So this document has two halves:

    rules              the closed set: every identifier iriguchi's own
                       components emit, each with one sentence
    open_namespaces    the prefixes where the second half of the identifier
                       comes from somebody else's detector

A consumer tests its locale file against `rules`, and falls back per prefix for
`open_namespaces` — *"detected by Presidio"* is a true and useful sentence even
when the entity type is one nobody has seen before.

## Why the Japanese ships here

Every entry carries `detail` and `detail_ja`, written by the same hand.

Sora reported that translating all of these themselves felt unsafe: they would
be inventing vocabulary they do not own, and if their wording disagreed with the
English **nobody could say which was right**. That instinct is correct, and the
fix is not for them to be braver. iriguchi owns the meaning of its own rules, so
iriguchi writes both sentences and the disagreement cannot arise.

Japanese specifically, and no other language. This project is written in
Japanese, about Japanese prompts, for an owner who reads it — so a Japanese
sentence here is authored, not translated. **French is deliberately absent**: it
would be exactly the invented vocabulary Sora was right to avoid, one level
further from anyone who could check it.

A rule with an English sentence and no Japanese one is refused by
`tests/test_the_rule_catalogue_is_complete.py`, so the pair cannot drift apart
the way two files would.

## Why this is a table and not a scan

Every entry needs a sentence a person can read, and prose cannot be derived from
a string literal. The table is written by hand, and
`tests/test_the_rule_catalogue_is_complete.py` walks the package's AST for
rule-shaped literals and fails if one is missing from it. **The staleness Sora
is trying to prevent is prevented on this side**, by the mechanism that would
otherwise have to be their CI noticing after the fact.

`iriguchi.rules/1-draft` is a draft: it freezes when a second program produces
and consumes it, which is the family's rule. Sora is the consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["CONTRACT", "OPEN_NAMESPACES", "RULES", "as_document"]

CONTRACT = "iriguchi.rules/1-draft"

#: Every rule identifier iriguchi's own components can put in a decision.
#:
#: The `detail` is one sentence about **what the rule means**, not what it did
#: on a particular prompt -- a decision's own `reasons[].detail` says that, and
#: repeating it here would be a second copy to drift.
RULES: tuple[tuple[str, str, str, str], ...] = (
    # -- the policy: which destination, and why. `domain/policy.py`.
    (
        "policy.prefer-local",
        "policy",
        "The complexity band did not call for the larger model, and a local model was permitted.",
        "複雑度が大きいモデルを必要としておらず、ローカルモデルが使えるため、ここで答えた。",
    ),
    (
        "policy.escalate-on-band",
        "policy",
        "The complexity band called for the larger model and the external "
        "destination was still permitted.",
        "複雑度が大きいモデルを必要としており、外部の宛先も許可されていた。",
    ),
    (
        "policy.only-destination",
        "policy",
        "One destination was left, so the preference axis had nothing to choose between.",
        "宛先が 1 つしか残っていないので、複雑度に選ぶ余地がなかった。",
    ),
    (
        "policy.finding-present",
        "policy",
        "A finding removed the external destination. Sensitivity is a veto: "
        "nothing on the other axis can restore it.",
        "検出があったため外部の宛先を取り除いた。感度は拒否権であり、複雑度がこれを覆すことはできない。",
    ),
    (
        "policy.every-destination-removed",
        "policy",
        "Every destination this machine has was removed by the veto, so the prompt was refused.",
        "この機械が持つ宛先がすべて拒否権で取り除かれたため、送らなかった。",
    ),
    (
        "policy.no-destination-available",
        "policy",
        "This machine has no destination configured at all. Not a refusal by "
        "the veto -- there was nowhere to send anything.",
        "この機械に宛先が 1 つも設定されていない。拒否権によるものではなく、送る先が無い。",
    ),
    # -- the router: what happened when a proposer failed. `application/routing.py`.
    (
        "scan.by-the-caller",
        "scan",
        "The findings came in with the prompt, from the caller's own analyzer. "
        "iriguchi did not look at this text -- so an empty set of findings here "
        "is the caller's clean bill of health, not iriguchi's.",
        "finding はプロンプトと一緒に渡された。呼び出し側自身の検出器のものである。"
        "iriguchi はこのテキストを見ていない。ここで finding が空なら、"
        "それは呼び出し側の「問題なし」であって、iriguchi のものではない。",
    ),
    (
        "scan.by-the-router",
        "scan",
        "iriguchi's own configured scanner looked and found nothing. The scanner "
        "is named in the detail, and what it misses is published -- an empty set "
        "of findings here is only as strong as that scanner.",
        "iriguchi 自身の（設定された）スキャナが見て、何も見つけなかった。"
        "どのスキャナかは detail に書いてある。取りこぼす範囲は公表してある。"
        "ここで finding が空であることの強さは、そのスキャナの強さまでである。",
    ),
    (
        "routing.scanner-failed",
        "routing",
        "The sensitivity scanner could not answer, so nothing is known about "
        "this prompt and it is treated as restricted (ADR-0002).",
        "感度スキャナが答えられなかった。このプロンプトについて何も分かっていないので、制限付きとして扱う（ADR-0002）。",
    ),
    (
        "routing.estimator-failed",
        "routing",
        "The complexity estimator could not answer, so the prompt is treated as "
        "the lowest band -- which routes local and costs answer quality, never "
        "privacy.",
        "複雑度推定が答えられなかった。最も低い帯として扱う。"
        "ローカルに留まるだけで、privacy は損なわれない。",
    ),
    # -- the cascade: whether a weak local answer may be re-asked. `domain/cascade.py`.
    (
        "cascade.weak-answer",
        "cascade",
        "The local answer looked weak and the external destination had never "
        "been removed for this prompt, so it was asked again.",
        "ローカルの回答が弱く、このプロンプトでは外部の宛先が一度も取り除かれていなかったので、もう一度尋ねた。",
    ),
    (
        "cascade.answer-was-adequate",
        "cascade",
        "The local answer showed no weakness worth escalating.",
        "ローカルの回答に、外に出すほどの弱さは見られなかった。",
    ),
    (
        "cascade.external-was-removed",
        "cascade",
        "The external destination was removed by a finding. A weak answer is "
        "evidence about a model, not about sensitivity.",
        "検出により外部の宛先が取り除かれている。弱い回答はモデルについての証拠であって、感度についての証拠ではない。",
    ),
    (
        "cascade.no-external-destination",
        "cascade",
        "There is no external service configured, so there was nowhere to "
        "escalate to. A missing endpoint rather than a refusal.",
        "外部サービスが設定されていないので、上げる先が無い。拒否ではなく、宛先の欠如である。",
    ),
    (
        "cascade.already-external",
        "cascade",
        "This prompt was already answered externally. A cascade escalates a "
        "local answer, and there is no larger destination beyond that one.",
        "このプロンプトは既に外部で答えられている。カスケードはローカルの回答を上げる仕組みで、その先に大きい宛先は無い。",
    ),
    (
        "cascade.nothing-was-answered",
        "cascade",
        "The prompt was refused, so there was no local answer to escalate from.",
        "プロンプトが拒否されたので、上げる元になるローカルの回答が無い。",
    ),
    (
        "cascade.judge-failed",
        "cascade",
        "The judge could not run, so the local answer stands unjudged. Not the "
        "same as an answer that looked fine.",
        "判定器が動かなかったので、ローカルの回答を未判定のまま採用した。回答が良く見えた、とは別のことである。",
    ),
    # -- the built-in scanner. `infrastructure/scanners/fallback.py`.
    (
        "fallback.email-shape",
        "fallback",
        "Something shaped like an email address.",
        "メールアドレスの形をしたものが含まれている。",
    ),
    (
        "fallback.private-key-block",
        "fallback",
        "A PEM private key block header.",
        "PEM 形式の秘密鍵ブロックの見出しが含まれている。",
    ),
    (
        "fallback.vendor-key-prefix",
        "fallback",
        "A token beginning with a prefix a vendor uses for API keys.",
        "ある事業者が API キーに使う接頭辞で始まるトークンが含まれている。",
    ),
    (
        "fallback.url-credentials",
        "fallback",
        "A URL carrying a username and password in its authority.",
        "利用者名とパスワードを URL の authority 部に含む URL がある。",
    ),
    (
        "fallback.credential-context",
        "fallback",
        "A word like `password` or `token` followed by a value.",
        "`password` や `token` のような語のあとに値が続いている。",
    ),
    (
        "fallback.long-digit-run",
        "fallback",
        "A long run of digits: a card number, an account number, or a "
        "harmless identifier. Reported because telling those apart needs "
        "context this scanner does not have.",
        "長い数字の並びがある。カード番号か、口座番号か、無害な識別子か。それを見分けるための文脈をこのスキャナは持たないので報告する。",
    ),
    (
        "fallback.japanese-honorific",
        "fallback",
        "A name followed by a Japanese honorific.",
        "敬称のついた名前が含まれている。",
    ),
    (
        "fallback.high-entropy-token",
        "fallback",
        "A token whose Shannon entropy is high enough to look generated rather than written.",
        "書かれたというより生成されたように見える、エントロピーの高いトークンがある。",
    ),
    # -- the complexity estimator. `infrastructure/estimators/rules.py`.
    (
        "complexity.multi-step",
        "complexity",
        "The request has more than one part, or asks why. Escalating.",
        "依頼が複数の部分に分かれているか、理由を問うている。エスカレーション対象。",
    ),
    (
        "complexity.formal-reasoning",
        "complexity",
        "A proof, a derivation, or a complexity argument. Escalating.",
        "証明・導出・計算量の議論を求めている。エスカレーション対象。",
    ),
    (
        "complexity.write-code",
        "complexity",
        "Writing or changing code, rather than reading it. Escalating.",
        "コードを読むのではなく、書くか変更することを求めている。エスカレーション対象。",
    ),
    (
        "complexity.code-block",
        "complexity",
        "The prompt contains a fenced code block.",
        "プロンプトにコードブロックが含まれている。",
    ),
    (
        "complexity.output-shape",
        "complexity",
        "The request asks for a particular output shape, such as JSON or a table.",
        "JSON や表など、出力の形を指定している。",
    ),
    (
        "complexity.several-questions",
        "complexity",
        "More than one question mark.",
        "疑問符が複数ある。",
    ),
    (
        "complexity.long-input",
        "complexity",
        "The prompt is long, measured in display columns rather than code "
        "points so the threshold means the same thing in every script.",
        "プロンプトが長い。コードポイントではなく表示幅で測るので、どの文字体系でも閾値の意味が変わらない。",
    ),
    (
        "complexity.dense-vocabulary",
        "complexity",
        "The mean ASCII word length reads as technical. Cannot fire on "
        "Japanese or Chinese, which have no spaces to split on.",
        "ASCII の平均語長が専門的に読める。空白で区切らない日本語や中国語では発火しない。",
    ),
    (
        "complexity.mixed-script",
        "complexity",
        "Japanese prose around English technical terms, which is the shape of a "
        "question about somebody else's documentation.",
        "英語の専門用語を日本語の地の文が囲んでいる。他人の文書についての質問によく見られる形。",
    ),
    # -- the answer judges, when a cascade is on. `infrastructure/judges/`.
    (
        "judge.refusal",
        "judge",
        "The local model said it could not help. Decisive: a model saying so "
        "has answered the question about its own adequacy.",
        "ローカルモデルが「答えられない」と述べた。決定的な合図である。自分が力不足かどうかは、モデル自身が答えたことになる。",
    ),
    (
        "judge.no-answer",
        "judge",
        "The local model returned nothing at all. The same information as a refusal.",
        "ローカルモデルが何も返さなかった。答えられないと述べたのと同じ情報である。",
    ),
    (
        "judge.truncated",
        "judge",
        "The answer stops without finishing a sentence.",
        "回答が文の途中で終わっている。",
    ),
    (
        "judge.repetition",
        "judge",
        "The same line repeated: a model that has come apart, and the shape "
        "signal with no innocent explanation.",
        "同じ行が繰り返されている。モデルが壊れた形であり、無害な説明のつかない唯一の形の合図。",
    ),
    (
        "judge.echoes-the-prompt",
        "judge",
        "The answer largely restates the request.",
        "回答が依頼をほぼ言い換えただけになっている。",
    ),
    (
        "judge.too-short-for-the-request",
        "judge",
        "A very short answer to a long request.",
        "長い依頼に対して回答が極端に短い。",
    ),
    (
        "judge.inconsistent",
        "judge",
        "Asked twice, the local model gave answers that disagree -- which is "
        "evidence about its confidence, not about whether it was right.",
        "二度尋ねたところ、ローカルモデルの回答が食い違った。確信度についての証拠であって、正しさについての証拠ではない。",
    ),
)

#: Prefixes whose second half iriguchi cannot know in advance.
#:
#: These are `f"{source}.{entity_type}"` where the entity type is whatever a
#: foreign detector returned. **A consumer should translate by prefix here**, and
#: a sentence naming the detector is true whatever the entity turns out to be.
OPEN_NAMESPACES: tuple[tuple[str, str, str], ...] = (
    (
        "presidio.",
        "Found by a Presidio analyzer -- either the optional `[presidio]` "
        "scanner or results a caller supplied with `--findings`. The rest of "
        "the identifier is Presidio's entity type, lower-cased, and which ones "
        "exist depends on the recognisers that install has.",
        "Presidio の analyzer が見つけたもの。任意の `[presidio]` スキャナか、"
        "`--findings` で渡された結果のどちらか。識別子の後半は Presidio の "
        "entity type を小文字にしたもので、どれが存在するかはその導入の "
        "recogniser 構成による。",
    ),
    (
        "mamori.",
        "Found by mamori's detectors. The rest of the identifier is mamori's "
        "entity type, lower-cased, and iriguchi never sees the full list.",
        "mamori の検出器が見つけたもの。識別子の後半は mamori の entity type を"
        "小文字にしたもので、iriguchi はその全体像を見ない。",
    ),
)


def as_document(version: str) -> Mapping[str, Any]:
    """The catalogue as `iriguchi.rules/1-draft`.

    `version` is passed in rather than read here, so this module imports
    nothing: it is a table, and a table that reaches for the package to learn
    its own version is a table with a dependency.
    """
    rules: Sequence[Mapping[str, str]] = [
        {"rule": rule, "source": source, "detail": detail, "detail_ja": japanese}
        for rule, source, detail, japanese in RULES
    ]
    return {
        "contract": CONTRACT,
        "by": f"iriguchi/{version}",
        "rules": rules,
        "open_namespaces": [
            {"prefix": prefix, "detail": detail, "detail_ja": japanese}
            for prefix, detail, japanese in OPEN_NAMESPACES
        ],
    }
