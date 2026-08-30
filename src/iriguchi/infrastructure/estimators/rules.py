"""How hard a prompt looks, from the text alone.

An estimator proposes signals; `domain/complexity.py` decides what they add up
to. Nothing here returns a band, and nothing here knows a destination exists.

**The residual, first, because it is the important part.** The routing
literature is consistent that *semantic* features dominate difficulty
prediction, with lexical and structural features as complementary indicators.
Semantic features need a model, and ADR-0004 refuses a model in the deciding
path -- so this estimator is built entirely from the complementary half and is,
by construction, the weaker of the two axes.

That is affordable only because complexity chooses between destinations
sensitivity has already cleared. Being wrong here costs answer quality and the
person says so. Being wrong on the other axis costs a leak and nobody says
anything.

**Two traps shaped the rules** (ADR-0007):

*Long and easy.* Four hundred lines of pasted log with "summarise this" on top.
Every router that scores on length sends this to the expensive model, so the
length rule's weight is deliberately too small to reach the top band alone.

*Short and hard.* Eleven characters asking for a proof. No amount of length,
shape or symbol counting sees this, which is what the two escalating families
are for: two of them reach the top band regardless of the weighted score.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.complexity import Signal, SignalKind
from ..normalization import normalize

__all__ = ["RulesEstimator"]

#: Characters long enough to be worth noticing. Not a difficulty threshold --
#: see the long-and-easy trap -- just the point past which a prompt stops being
#: a sentence.
_LONG_INPUT = 600

#: What an escalating marker is worth on its own. Chosen so that one reaches the
#: middle band (0.45) and two do *not* reach the top by score alone:
#: 1 - 0.55^2 = 0.6975, just under 0.7. The short-circuit is what takes them the
#: rest of the way, and keeping that gap is what makes it testable rather than a
#: rule that happens to agree with the arithmetic.
_ESCALATING_WEIGHT = 0.45


@dataclass(frozen=True, slots=True)
class _Marker:
    """A rule that fires on finding a phrase, and points at the first one."""

    id: str
    kind: SignalKind
    pattern: re.Pattern[str]
    weight: float
    escalating: bool = False


_MARKERS: tuple[_Marker, ...] = (
    # A fenced block, or four or more lines that look like an assignment or a
    # call. Leans toward noticing: reading code is not automatically hard, but
    # it is reliably harder than the prose around it.
    _Marker(
        "complexity.code-block",
        SignalKind.STRUCTURAL,
        re.compile(r"```|(?:^[ \t]*\S+[ \t]*[=(][^\n]*\n){4,}", re.MULTILINE),
        0.35,
    ),
    # Asking for a shape is asking for instruction-following, which is where
    # small models fall down first -- more reliably than on the content.
    _Marker(
        "complexity.output-shape",
        SignalKind.STRUCTURAL,
        re.compile(
            r"(?i:json|yaml|csv|markdown|xml)\s*(?:で|形式|format)"
            r"|(?:表|テーブル|箇条書き|マークダウン)\s*(?:に|で|形式)"
            r"|(?i:as (?:a )?(?:table|list|json|csv|markdown))",
        ),
        0.2,
    ),
    # Two or more question marks, in either width. Several questions in one
    # prompt is several answers, and the second is usually the one a small model
    # drops.
    _Marker(
        "complexity.several-questions",
        SignalKind.STRUCTURAL,
        re.compile(r"[?？][^?？]*[?？]", re.DOTALL),
        0.25,
    ),
    # ESCALATING. A request that has more than one part, or that asks *why*.
    # Deliberately not `and`: conjunctions are everywhere and mean nothing.
    _Marker(
        "complexity.multi-step",
        SignalKind.STRUCTURAL,
        re.compile(
            r"比較|対比|検討|分析|考察|評価|レビュー|設計|なぜ|理由"
            r"|(?i:\bcompare\b|\bcontrast\b|\banaly[sz]e\b|\bevaluate\b|\breview\b"
            r"|\bdesign\b|\bwhy\b|step by step)"
        ),
        _ESCALATING_WEIGHT,
        escalating=True,
    ),
    # ESCALATING. Formal work: a proof, a derivation, a complexity argument.
    # The narrowest rule here and the one least likely to be wrong -- nobody
    # writes `計算量` casually.
    _Marker(
        "complexity.formal-reasoning",
        SignalKind.STRUCTURAL,
        re.compile(
            r"証明|導出|補題|定理|計算量|最適化|アルゴリズム"
            r"|(?i:\bprove\b|\bproof\b|\bderive\b|\btheorem\b|\blemma\b"
            r"|\bcomplexity\b|\boptimi[sz]e\b|\balgorithm\b)"
        ),
        _ESCALATING_WEIGHT,
        escalating=True,
    ),
    # ESCALATING. Writing or changing code, as opposed to reading it. The
    # clearest line between what a 3B model does adequately and what it does
    # not.
    _Marker(
        "complexity.write-code",
        SignalKind.STRUCTURAL,
        re.compile(
            r"実装|リファクタ|コードを書|関数を書|バグ|デバッグ"
            r"|(?i:\bimplement\b|\brefactor\b|\bdebug\b"
            r"|write (?:a |the )?(?:function|class|script))"
        ),
        _ESCALATING_WEIGHT,
        escalating=True,
    ),
)

_ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")

#: Mean ASCII word length above which the vocabulary reads as technical. Seven
#: is roughly where `implementation`, `authentication` and `serialization` live
#: and ordinary prose does not.
_DENSE_WORD_LENGTH = 7.0
#: Below this many words the mean is noise: two long words in a five-word
#: sentence is not a technical document.
_DENSE_MIN_WORDS = 20
#: Both scripts have to be present in more than a token amount. A single English
#: product name in a Japanese sentence is not mixed script in any sense that
#: bears on difficulty.
_MIXED_SCRIPT_MIN_SHARE = 0.1


class RulesEstimator:
    """The estimator iriguchi ships with. Rules, and no model."""

    name = "rules"

    def estimate(self, text: str) -> Sequence[Signal]:
        """Every reason this text might be harder than it looks.

        Matching happens on NFKC-folded text -- `ＪＳＯＮで出力して` is a
        request for a shape -- and spans are mapped back before they are
        returned, exactly as the scanner does it.

        At most one signal per rule. Findings may repeat because three
        addresses are three findings; a signal is a statement about the request,
        and counting `比較` four times would let one long prompt manufacture its
        own escalation.
        """
        if not text.strip():
            return ()

        folded = normalize(text)
        signals: list[Signal] = list(self._lexical(folded.text))

        for marker in _MARKERS:
            match = marker.pattern.search(folded.text)
            if match is None:
                continue
            signals.append(
                Signal(
                    rule=marker.id,
                    kind=marker.kind,
                    weight=marker.weight,
                    escalating=marker.escalating,
                    span=folded.to_original(*match.span()),
                )
            )

        signals.sort(key=lambda signal: signal.rule)
        return tuple(signals)

    def _lexical(self, folded: str) -> list[Signal]:
        """Properties of the whole request, so none of these carries a span.

        A span of `0-4000` in an explanation tells a reader nothing they did not
        already know, and `None` renders as a statement about the prompt rather
        than about a place in it.
        """
        signals: list[Signal] = []

        if len(folded) >= _LONG_INPUT:
            # **The long-and-easy trap lives here.** A pasted log is long and
            # trivial, so this weight has to stay well under the top band on its
            # own. It is evidence, not a verdict.
            signals.append(Signal("complexity.long-input", SignalKind.LEXICAL, 0.3, span=None))

        words = _ASCII_WORD.findall(folded)
        if len(words) >= _DENSE_MIN_WORDS:
            mean_length = sum(len(word) for word in words) / len(words)
            if mean_length >= _DENSE_WORD_LENGTH:
                # A proxy for rare vocabulary, and an admitted one. Real
                # rare-word rate needs a frequency list, which is data this
                # library does not carry; mean token length correlates with it
                # and is wrong on, among other things, German.
                signals.append(
                    Signal("complexity.dense-vocabulary", SignalKind.LEXICAL, 0.25, span=None)
                )

        if folded:
            cjk = len(_CJK.findall(folded)) / len(folded)
            latin = len(_LATIN.findall(folded)) / len(folded)
            if cjk >= _MIXED_SCRIPT_MIN_SHARE and latin >= _MIXED_SCRIPT_MIN_SHARE:
                # Japanese prose around English technical terms is the shape of
                # a question about someone else's documentation, which is
                # reliably harder than a question about the prose alone.
                signals.append(
                    Signal("complexity.mixed-script", SignalKind.LEXICAL, 0.2, span=None)
                )

        return signals
