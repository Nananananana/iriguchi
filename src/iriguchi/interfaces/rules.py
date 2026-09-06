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
RULES: tuple[tuple[str, str, str], ...] = (
    # -- the policy: which destination, and why. `domain/policy.py`.
    (
        "policy.prefer-local",
        "policy",
        "The complexity band did not call for the larger model, and a local model was permitted.",
    ),
    (
        "policy.escalate-on-band",
        "policy",
        "The complexity band called for the larger model and the external "
        "destination was still permitted.",
    ),
    (
        "policy.only-destination",
        "policy",
        "One destination was left, so the preference axis had nothing to choose between.",
    ),
    (
        "policy.finding-present",
        "policy",
        "A finding removed the external destination. Sensitivity is a veto: "
        "nothing on the other axis can restore it.",
    ),
    (
        "policy.every-destination-removed",
        "policy",
        "Every destination this machine has was removed by the veto, so the prompt was refused.",
    ),
    (
        "policy.no-destination-available",
        "policy",
        "This machine has no destination configured at all. Not a refusal by "
        "the veto -- there was nowhere to send anything.",
    ),
    # -- the router: what happened when a proposer failed. `application/routing.py`.
    (
        "routing.scanner-failed",
        "routing",
        "The sensitivity scanner could not answer, so nothing is known about "
        "this prompt and it is treated as restricted (ADR-0002).",
    ),
    (
        "routing.estimator-failed",
        "routing",
        "The complexity estimator could not answer, so the prompt is treated as "
        "the lowest band -- which routes local and costs answer quality, never "
        "privacy.",
    ),
    # -- the cascade: whether a weak local answer may be re-asked. `domain/cascade.py`.
    (
        "cascade.weak-answer",
        "cascade",
        "The local answer looked weak and the external destination had never "
        "been removed for this prompt, so it was asked again.",
    ),
    (
        "cascade.answer-was-adequate",
        "cascade",
        "The local answer showed no weakness worth escalating.",
    ),
    (
        "cascade.external-was-removed",
        "cascade",
        "The external destination was removed by a finding. A weak answer is "
        "evidence about a model, not about sensitivity.",
    ),
    (
        "cascade.no-external-destination",
        "cascade",
        "There is no external service configured, so there was nowhere to "
        "escalate to. A missing endpoint rather than a refusal.",
    ),
    (
        "cascade.already-external",
        "cascade",
        "This prompt was already answered externally. A cascade escalates a "
        "local answer, and there is no larger destination beyond that one.",
    ),
    (
        "cascade.nothing-was-answered",
        "cascade",
        "The prompt was refused, so there was no local answer to escalate from.",
    ),
    (
        "cascade.judge-failed",
        "cascade",
        "The judge could not run, so the local answer stands unjudged. Not the "
        "same as an answer that looked fine.",
    ),
    # -- the built-in scanner. `infrastructure/scanners/fallback.py`.
    ("fallback.email-shape", "fallback", "Something shaped like an email address."),
    ("fallback.private-key-block", "fallback", "A PEM private key block header."),
    (
        "fallback.vendor-key-prefix",
        "fallback",
        "A token beginning with a prefix a vendor uses for API keys.",
    ),
    (
        "fallback.url-credentials",
        "fallback",
        "A URL carrying a username and password in its authority.",
    ),
    (
        "fallback.credential-context",
        "fallback",
        "A word like `password` or `token` followed by a value.",
    ),
    (
        "fallback.long-digit-run",
        "fallback",
        "A long run of digits: a card number, an account number, or a "
        "harmless identifier. Reported because telling those apart needs "
        "context this scanner does not have.",
    ),
    (
        "fallback.japanese-honorific",
        "fallback",
        "A name followed by a Japanese honorific.",
    ),
    (
        "fallback.high-entropy-token",
        "fallback",
        "A token whose Shannon entropy is high enough to look generated rather than written.",
    ),
    # -- the complexity estimator. `infrastructure/estimators/rules.py`.
    (
        "complexity.multi-step",
        "complexity",
        "The request has more than one part, or asks why. Escalating.",
    ),
    (
        "complexity.formal-reasoning",
        "complexity",
        "A proof, a derivation, or a complexity argument. Escalating.",
    ),
    (
        "complexity.write-code",
        "complexity",
        "Writing or changing code, rather than reading it. Escalating.",
    ),
    ("complexity.code-block", "complexity", "The prompt contains a fenced code block."),
    (
        "complexity.output-shape",
        "complexity",
        "The request asks for a particular output shape, such as JSON or a table.",
    ),
    ("complexity.several-questions", "complexity", "More than one question mark."),
    (
        "complexity.long-input",
        "complexity",
        "The prompt is long, measured in display columns rather than code "
        "points so the threshold means the same thing in every script.",
    ),
    (
        "complexity.dense-vocabulary",
        "complexity",
        "The mean ASCII word length reads as technical. Cannot fire on "
        "Japanese or Chinese, which have no spaces to split on.",
    ),
    (
        "complexity.mixed-script",
        "complexity",
        "Japanese prose around English technical terms, which is the shape of a "
        "question about somebody else's documentation.",
    ),
    # -- the answer judges, when a cascade is on. `infrastructure/judges/`.
    (
        "judge.refusal",
        "judge",
        "The local model said it could not help. Decisive: a model saying so "
        "has answered the question about its own adequacy.",
    ),
    (
        "judge.no-answer",
        "judge",
        "The local model returned nothing at all. The same information as a refusal.",
    ),
    ("judge.truncated", "judge", "The answer stops without finishing a sentence."),
    (
        "judge.repetition",
        "judge",
        "The same line repeated: a model that has come apart, and the shape "
        "signal with no innocent explanation.",
    ),
    ("judge.echoes-the-prompt", "judge", "The answer largely restates the request."),
    (
        "judge.too-short-for-the-request",
        "judge",
        "A very short answer to a long request.",
    ),
    (
        "judge.inconsistent",
        "judge",
        "Asked twice, the local model gave answers that disagree -- which is "
        "evidence about its confidence, not about whether it was right.",
    ),
)

#: Prefixes whose second half iriguchi cannot know in advance.
#:
#: These are `f"{source}.{entity_type}"` where the entity type is whatever a
#: foreign detector returned. **A consumer should translate by prefix here**, and
#: a sentence naming the detector is true whatever the entity turns out to be.
OPEN_NAMESPACES: tuple[tuple[str, str], ...] = (
    (
        "presidio.",
        "Found by a Presidio analyzer -- either the optional `[presidio]` "
        "scanner or results a caller supplied with `--findings`. The rest of "
        "the identifier is Presidio's entity type, lower-cased, and which ones "
        "exist depends on the recognisers that install has.",
    ),
    (
        "mamori.",
        "Found by mamori's detectors. The rest of the identifier is mamori's "
        "entity type, lower-cased, and iriguchi never sees the full list.",
    ),
)


def as_document(version: str) -> Mapping[str, Any]:
    """The catalogue as `iriguchi.rules/1-draft`.

    `version` is passed in rather than read here, so this module imports
    nothing: it is a table, and a table that reaches for the package to learn
    its own version is a table with a dependency.
    """
    rules: Sequence[Mapping[str, str]] = [
        {"rule": rule, "source": source, "detail": detail} for rule, source, detail in RULES
    ]
    return {
        "contract": CONTRACT,
        "by": f"iriguchi/{version}",
        "rules": rules,
        "open_namespaces": [
            {"prefix": prefix, "detail": detail} for prefix, detail in OPEN_NAMESPACES
        ],
    }
