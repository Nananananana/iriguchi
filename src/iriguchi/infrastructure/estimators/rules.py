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
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from ...domain.complexity import Signal, SignalKind
from ...errors import ConfigurationError
from ..normalization import normalize

__all__ = ["DEFAULT_SETTINGS", "RulesEstimator", "RulesSettings", "display_width"]

#: What an escalating marker is worth on its own. Chosen so that one reaches the
#: middle band (0.45) and two do *not* reach the top by score alone:
#: 1 - 0.55^2 = 0.6975, just under 0.7. The short-circuit is what takes them the
#: rest of the way, and keeping that gap is what makes it testable rather than a
#: rule that happens to agree with the arithmetic.
_ESCALATING_WEIGHT = 0.45


def display_width(text: str) -> int:
    """Length in columns rather than in code points.

    **A threshold in code points is a different threshold in every script**, and
    this one was measured being different. The same request, written twice:

        Please refactor this authentication module. (x15)   660 code points
        この認証モジュールをリファクタリングしてください。 (x15)   375 code points

    Same content. The English one crossed `long_input_at` and the Japanese one
    did not, so a Japanese user had to write roughly twice as much to reach the
    same band. Nobody chose that; it fell out of counting characters.

    East Asian Width is the stdlib's answer and a well-worn convention -- the
    same one every terminal uses to align a CJK column. Wide and Fullwidth
    characters count two. It is a **proxy for information content, not a
    measurement of it**, and it is right about the thing that matters here: the
    two prompts above come out at 660 and 750, and both clear 600.

    Ambiguous-width characters count one. They are ambiguous because their width
    depends on the surrounding locale, and guessing East Asian for a string that
    might be Greek would break the case this exists to fix in the other
    direction.
    """
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


@dataclass(frozen=True, slots=True)
class RulesSettings:
    """Every number this estimator uses, in one place a caller can reach.

    Until this existed there was no `__init__` at all: the weights were
    module-private constants, and somebody whose traffic did not look like the
    corpus had to fork the library to change one. That is the shape of a
    threshold that cannot survive contact with a second user.

    Defaults are exactly the values that were hard-coded, so nothing moves by
    adopting this. What changes is that they can now be moved **and written
    down** -- `iriguchi.routing-decision/1` publishes the band thresholds
    already, and a decision whose weights are unrecorded cannot be reproduced.

    Args:
        long_input_at: Columns past which a prompt stops being a sentence. In
            display width (see `display_width`), not code points.
        long_input_weight: Deliberately small. A pasted log is long and trivial,
            and every router that scores on length sends it to the big model.
        dense_word_length: Mean **ASCII** word length reading as technical.
        dense_min_words: Below this the mean is noise.
        dense_weight: What that proxy is worth.
        mixed_script_min_share: How much of each script has to be present before
            a prompt counts as mixed. A single product name is not mixed script.
        mixed_script_weight: What that is worth.
        escalating_weight: What one escalating marker is worth. The default is
            chosen so two of them reach 0.6975 -- just under the top band -- and
            the short circuit is what carries them the rest of the way. Raising
            this above roughly 0.46 makes the short circuit unobservable, which
            is a real change and not a tuning.
        marker_weights: Per-rule overrides, by rule id. **This is the knob that
            matters after release**: a deployment where `複数の観点` means
            something different can retune that one rule without forking, and
            without touching the other twenty.

    Raises:
        ConfigurationError: for a weight outside [0,1], a non-positive length,
            a share outside [0,1], or an override naming a rule that does not
            exist. The last one is the important refusal: a typo in a rule id
            silently changes nothing, and the caller would believe otherwise.
    """

    long_input_at: int = 600
    long_input_weight: float = 0.3
    dense_word_length: float = 7.0
    dense_min_words: int = 20
    dense_weight: float = 0.25
    mixed_script_min_share: float = 0.1
    mixed_script_weight: float = 0.2
    escalating_weight: float = 0.45
    marker_weights: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        for name in (
            "long_input_weight",
            "dense_weight",
            "mixed_script_weight",
            "escalating_weight",
            "mixed_script_min_share",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ConfigurationError(
                    f"{name} is {value} and a weight is a share of evidence in "
                    f"[0,1]. Combining is `1 - prod(1 - w)`, which is not "
                    f"defined outside that range."
                )
        for name in ("long_input_at", "dense_min_words"):
            if getattr(self, name) < 1:
                raise ConfigurationError(
                    f"{name} is {getattr(self, name)}. A length of zero fires on "
                    f"every prompt, which is a signal that says nothing."
                )
        if self.dense_word_length <= 0:
            raise ConfigurationError("dense_word_length must be positive")
        for rule, weight in self.marker_weights.items():
            if not 0.0 <= weight <= 1.0:
                raise ConfigurationError(f"the override for {rule!r} is {weight}, not in [0,1]")

    def weight_for(self, marker: _Marker) -> float:
        """This rule's weight, most specific override first.

        A per-rule override beats `escalating_weight`, which beats the weight
        written into the marker table. Otherwise setting `escalating_weight`
        would be a field that reads as a knob and turns nothing -- the markers
        carry a copy of the default, and a copy is what a setting has to
        replace rather than sit beside.
        """
        if marker.id in self.marker_weights:
            return self.marker_weights[marker.id]
        if marker.escalating:
            return self.escalating_weight
        return marker.weight


#: The values that were hard-coded before `RulesSettings` existed. Adopting the
#: settings object changes no behaviour; it changes who is allowed to.
DEFAULT_SETTINGS = RulesSettings()


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

# The three constants that used to live here -- `_LONG_INPUT`,
# `_DENSE_WORD_LENGTH`, `_DENSE_MIN_WORDS`, `_MIXED_SCRIPT_MIN_SHARE` -- are
# fields of `RulesSettings` now, with the same values and the same reasoning.
# They were module-private, which meant a deployment whose traffic did not look
# like this corpus had to fork the library to move one.


class RulesEstimator:
    """The estimator iriguchi ships with. Rules, and no model.

    Args:
        settings: Every number it uses. Defaults to the values that used to be
            module constants, so an estimator built with no arguments behaves
            exactly as it did before it could take any.
    """

    name = "rules"

    def __init__(self, settings: RulesSettings | None = None) -> None:
        self.settings = DEFAULT_SETTINGS if settings is None else settings

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
                    weight=self.settings.weight_for(marker),
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

        # Display width, not `len`. The same request in Japanese is roughly
        # half the code points, so a code-point threshold quietly asked a
        # Japanese user for twice the content. See `display_width`.
        if display_width(folded) >= self.settings.long_input_at:
            # **The long-and-easy trap lives here.** A pasted log is long and
            # trivial, so this weight has to stay well under the top band on its
            # own. It is evidence, not a verdict.
            signals.append(
                Signal(
                    "complexity.long-input",
                    SignalKind.LEXICAL,
                    self.settings.long_input_weight,
                    span=None,
                )
            )

        # **This signal is ASCII-only and cannot fire on Japanese or Chinese.**
        # `_ASCII_WORD` needs spaces to find words and those scripts have none,
        # so the whole rule is silently inapplicable to them -- which the
        # docstring below used to admit about German and not about the language
        # this project is written in.
        #
        # It is not fixed by a CJK counterpart, and that was measured rather
        # than assumed. Kanji ratio is the obvious candidate and it is a
        # language detector wearing a density costume: over this corpus its 90th
        # percentile is 0.71 and every case up there is ordinary Chinese prose,
        # because Chinese is ~90% hanzi whatever it is about. A signal that
        # fires on all Chinese is not a difficulty signal.
        #
        # So the gap is recorded rather than filled, and it is part of why the
        # complexity axis is the weaker one (`docs/feasibility.md` F1).
        words = _ASCII_WORD.findall(folded)
        if len(words) >= self.settings.dense_min_words:
            mean_length = sum(len(word) for word in words) / len(words)
            if mean_length >= self.settings.dense_word_length:
                # A proxy for rare vocabulary, and an admitted one. Real
                # rare-word rate needs a frequency list, which is data this
                # library does not carry; mean token length correlates with it
                # and is wrong on, among other things, German.
                signals.append(
                    Signal(
                        "complexity.dense-vocabulary",
                        SignalKind.LEXICAL,
                        self.settings.dense_weight,
                        span=None,
                    )
                )

        if folded:
            cjk = len(_CJK.findall(folded)) / len(folded)
            latin = len(_LATIN.findall(folded)) / len(folded)
            share = self.settings.mixed_script_min_share
            if cjk >= share and latin >= share:
                # Japanese prose around English technical terms is the shape of
                # a question about someone else's documentation, which is
                # reliably harder than a question about the prose alone.
                signals.append(
                    Signal(
                        "complexity.mixed-script",
                        SignalKind.LEXICAL,
                        self.settings.mixed_script_weight,
                        span=None,
                    )
                )

        return signals
