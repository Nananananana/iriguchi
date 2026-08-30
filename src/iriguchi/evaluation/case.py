"""One labelled prompt, and what is expected of it.

A case labels two things and derives the third. It says what a *correct*
sensitivity classification would be and what band the request belongs in; it
does **not** say which route should come out.

That omission is deliberate. The route follows from the two labels by way of
`RoutingPolicy`, and writing it into the fixture would copy the policy into the
corpus -- after which a policy change would require a corpus edit to stay
"correct", and a corpus that has to be edited to agree with the code has stopped
being evidence about the code.

So the scorer asks the policy what the labels imply, and compares that with what
the router actually decided. What is being measured is the two proposers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.complexity import ComplexityBand

__all__ = ["Case", "SensitivityClass", "TrapKind"]


class SensitivityClass(Enum):
    """What a correct scanner would conclude about this prompt.

    Two members, matching `SensitivityLevel`, because the corpus measures the
    scanner against the same two-valued question the domain asks.
    """

    #: Something in here would identify a person, an organisation or a secret.
    MUST_STAY_LOCAL = "must_stay_local"
    #: Nothing in here would. The half that measures over-detection, and the
    #: half a corpus without it cannot measure at all.
    MAY_LEAVE = "may_leave"


class TrapKind(Enum):
    """What makes a case able to fail a wrong implementation.

    A corpus of obvious cases measures nothing, because every router passes it.
    tsumugi found this on its first eval run; the list below is ADR-0007's,
    which is that finding applied to routing.

    A closed set on purpose. A new kind of adversary is a visible change to what
    the corpus claims to cover.

    It is also a ceiling: seven kinds chosen by one person, so this corpus can
    only fail an implementation in seven ways that person had already imagined.
    ADR-0007's cost section says what widening it would take, and it is not more
    cases.
    """

    #: No adversary. Included so the corpus has a baseline, and kept in a
    #: minority so it cannot flatter the numbers.
    PLAIN = "plain"
    #: Looks sensitive, is not: a public documentation URL, a fictional
    #: character, a vendor's own sample key.
    LOOKS_SENSITIVE = "looks_sensitive"
    #: Looks trivial, is not safe: "translate this", and a key in the paragraph.
    HIDDEN_SECRET = "hidden_secret"  # noqa: S105 -- a trap kind, not a credential
    #: Long and easy. A pasted log with "summarise this" -- length is not
    #: difficulty, and every router that scores on length gets this wrong.
    LONG_AND_EASY = "long_and_easy"
    #: Short and hard. Four words that no small model will answer.
    SHORT_AND_HARD = "short_and_hard"
    #: Japanese prose around an English code block.
    MIXED_SCRIPT = "mixed_script"
    #: The secret is in an attached tool-call payload, not the sentence.
    #: mamori's ADR-0030 found this one.
    OUTSIDE_THE_PROSE = "outside_the_prose"
    #: One character's difference flips the decision, and the reason has to name
    #: that character.
    NEAR_DUPLICATE = "near_duplicate"


@dataclass(frozen=True, slots=True)
class Case:
    """A prompt, its labels, and why it is here."""

    id: str
    prompt: str
    sensitivity: SensitivityClass
    #: The band a correct estimator would reach. The weaker of the two labels,
    #: and knowingly so: there is no ground truth for "how hard is this", only a
    #: judgement about what a 3B model would manage.
    band: ComplexityBand
    trap: TrapKind
    #: Where the prompt came from: `generated`, `borrowed:mamori/ja-core`.
    #: Kept so a bad number can be attributed to a source rather than to the
    #: corpus as a whole.
    source: str
    #: Required for anything that is not `PLAIN`, and for anything a reader
    #: would otherwise "fix". A trap with no note is a case the next person
    #: relabels.
    note: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a case must have an id")
        if not self.prompt.strip():
            raise ValueError(f"case {self.id} has no prompt")
        if self.trap is not TrapKind.PLAIN and not self.note:
            raise ValueError(
                f"case {self.id} is a {self.trap.value} trap with no note. Say what the "
                "adversary is, or the next reader will relabel the case instead of "
                "believing it."
            )
