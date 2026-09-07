"""Every rule iriguchi can emit is in the catalogue, checked against the source.

Sora keys three languages of translation off `rule` and asked for a list so its
CI can fail when a translation is missing (R7). The failure they want to prevent
is iriguchi adding a rule and their screen showing `policy.something-new` in raw
ASCII to somebody reading Japanese.

A hand-written list would be the same bug one level up: it goes stale the day
somebody adds a rule and forgets, which is exactly the day it matters. So the
list is written by hand -- every entry needs a sentence, and prose cannot be
derived from a string literal -- and **this file walks the package's syntax tree
and fails if a rule-shaped identifier is not in it.**

The staleness is prevented on iriguchi's side, rather than by Sora's CI noticing
afterwards.

## The two shapes a rule id is written in

    "policy.prefer-local"                    a literal, found by the scan
    f"{SOURCE}.{rule}"  with SOURCE="cascade"    assembled, and not found

The second is why the scan alone is not enough, and why the assembled families
are listed here with the constant that builds them. A family that grows a
seventh member without this file learning about it is caught by
`test_every_assembled_family_is_complete`, which builds them for real.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from iriguchi.interfaces.rules import CONTRACT, OPEN_NAMESPACES, RULES, as_document

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "iriguchi"

#: The namespaces this project owns. `presidio.` and `mamori.` are deliberately
#: absent: their second half is a foreign detector's entity type.
OWNED = ("policy", "routing", "cascade", "fallback", "complexity", "judge")

#: A rule-shaped string literal in one of the owned namespaces.
LITERAL = re.compile(rf"^(?:{'|'.join(OWNED)})\.[a-z0-9-]+$")

CATALOGUE = {rule for rule, *_ in RULES}


def _string_literals() -> set[str]:
    """Every plain string constant in the package, from the syntax tree.

    Parsed rather than grepped: a rule id inside a comment or a docstring is
    prose about a rule, not a rule, and this file would otherwise demand a
    catalogue entry for an identifier nothing emits.
    """
    found: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value not in docstrings
            ):
                found.add(node.value)
    return found


class TestTheScanFindsSomething:
    """Floors. Every assertion below is vacuous over an empty set."""

    def test_the_package_parses_and_yields_literals(self) -> None:
        assert len(_string_literals()) > 100

    def test_the_catalogue_is_not_empty(self) -> None:
        assert len(CATALOGUE) >= 30

    def test_the_pattern_matches_a_known_rule(self) -> None:
        assert LITERAL.match("policy.prefer-local")
        assert not LITERAL.match("presidio.person")
        assert not LITERAL.match("policy")


class TestEveryEmittedRuleIsListed:
    def test_no_literal_rule_is_missing_from_the_catalogue(self) -> None:
        """The mechanism. Add `Reason(rule="policy.something-new", ...)` and
        this goes red before it can reach anybody's screen untranslated."""
        emitted = {value for value in _string_literals() if LITERAL.match(value)}
        missing = sorted(emitted - CATALOGUE)
        assert not missing, (
            f"{missing} can appear in a decision and are not in "
            f"`interfaces/rules.py`. A consumer keys its translations off "
            f"`rule`, so an unlisted one reaches a reader as raw ASCII."
        )

    def test_the_catalogue_lists_nothing_that_cannot_be_emitted(self) -> None:
        """The other direction. A rule that was renamed and left behind here
        would have a consumer carrying a translation for something that never
        arrives, and quietly believing it was covered.

        Assembled families are exempt from the literal scan and are checked by
        the test below instead.
        """
        emitted = {value for value in _string_literals() if LITERAL.match(value)}
        assembled = {"cascade", "judge"}
        stale = sorted(
            rule for rule in CATALOGUE - emitted if rule.split(".", 1)[0] not in assembled
        )
        assert not stale, f"{stale} are in the catalogue and nothing emits them"

    @pytest.mark.parametrize("rule,source,detail,japanese", RULES, ids=[r for r, *_ in RULES])
    def test_every_entry_says_what_it_means(
        self, rule: str, source: str, detail: str, japanese: str
    ) -> None:
        assert rule.startswith(f"{source}."), (rule, source)
        assert source in OWNED
        assert detail.endswith("."), f"{rule}'s detail is not a sentence"
        assert len(detail.split()) >= 5, f"{rule}'s detail is a shrug"
        # The Japanese is authored here rather than by a consumer, so that a
        # disagreement between the two cannot arise -- and it is checked here
        # so the pair cannot drift apart the way two files would.
        assert japanese.strip(), f"{rule} has no Japanese sentence"
        assert japanese.endswith("。"), f"{rule}'s Japanese is not a sentence"
        assert japanese != detail, f"{rule}'s Japanese is the English"
        assert any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in japanese), (
            f"{rule}'s Japanese contains no Japanese"
        )

    def test_no_rule_is_listed_twice(self) -> None:
        assert len(CATALOGUE) == len(RULES)


class TestTheAssembledFamilies:
    """`f"{SOURCE}.{rule}"` cannot be found by scanning for literals.

    So they are built for real and compared, which is stronger than the scan:
    it runs the code that makes them.
    """

    def test_every_cascade_verdict_is_listed(self) -> None:
        """Every branch of `may_escalate`, driven to produce its reason."""
        from iriguchi.domain.answer import AnswerQuality, AnswerSignal, Weakness
        from iriguchi.domain.cascade import may_escalate
        from iriguchi.domain.complexity import Complexity, ComplexityBand
        from iriguchi.domain.decision import RoutingDecision
        from iriguchi.domain.destination import Destination, Route
        from iriguchi.domain.reason import Reason, Removal
        from iriguchi.domain.sensitivity import Sensitivity, SensitivityLevel

        both = frozenset({Destination.LOCAL, Destination.EXTERNAL})
        weak = AnswerQuality.from_signals(
            [AnswerSignal("judge.refusal", Weakness.STATED, 0.95, decisive=True)]
        )
        fine = AnswerQuality.from_signals([])

        def decision(route: Route, *, removed: bool = False) -> RoutingDecision:
            taken = (
                (
                    Removal(
                        destination=Destination.EXTERNAL,
                        reason=Reason(
                            rule="policy.finding-present",
                            source="policy",
                            span=None,
                            detail="a finding",
                        ),
                    ),
                )
                if removed
                else ()
            )
            return RoutingDecision(
                route=route,
                sensitivity=Sensitivity(level=SensitivityLevel.CLEAR, findings=()),
                complexity=Complexity(band=ComplexityBand.LOW, score=0.0),
                removed=taken,
            )

        produced = {
            may_escalate(decision(Route.REFUSED), weak, both).reason.rule,
            may_escalate(decision(Route.EXTERNAL), weak, both).reason.rule,
            may_escalate(decision(Route.LOCAL), weak, frozenset({Destination.LOCAL})).reason.rule,
            may_escalate(decision(Route.LOCAL, removed=True), weak, both).reason.rule,
            may_escalate(decision(Route.LOCAL), fine, both).reason.rule,
            may_escalate(decision(Route.LOCAL), weak, both).reason.rule,
        }
        assert len(produced) == 6, produced
        assert produced <= CATALOGUE, sorted(produced - CATALOGUE)

    def test_every_judge_signal_is_listed(self) -> None:
        """Both judges, driven to emit every signal they have."""
        from iriguchi.infrastructure.judges import ConsistencyJudge, ConsistencySettings, RulesJudge

        class _Model:
            name = "fake"

            def answer(self, prompt: str) -> str:
                return "something else entirely"

        rules = RulesJudge()
        produced = {
            signal.rule
            for prompt, answer in (
                ("q", ""),
                ("q", "I do not know."),
                ("q", "Because"),
                ("q", "same\nsame\nsame\nend."),
                ("alpha beta gamma", "alpha beta gamma alpha beta gamma"),
                ("x" * 400, "no."),
            )
            for signal in rules.judge(prompt, answer)
        }
        produced |= {
            signal.rule
            for signal in ConsistencyJudge(_Model(), ConsistencySettings(agrees_above=1.0)).judge(
                "q", "an answer"
            )
        }
        assert len(produced) == 7, sorted(produced)
        assert produced <= CATALOGUE, sorted(produced - CATALOGUE)


class TestTheDocument:
    def test_it_names_the_contract_first(self) -> None:
        document = as_document("0.1.0")
        assert next(iter(document)) == "contract"
        assert document["contract"] == CONTRACT

    def test_it_carries_the_producer_version(self) -> None:
        assert as_document("9.9.9")["by"] == "iriguchi/9.9.9"

    def test_every_rule_appears_once_with_its_sentence(self) -> None:
        rules = as_document("0.1.0")["rules"]
        assert len(rules) == len(RULES)
        assert all(set(entry) == {"rule", "source", "detail", "detail_ja"} for entry in rules)

    def test_every_rule_carries_both_sentences(self) -> None:
        """`detail` is English and `detail_ja` is Japanese, both authored here.

        Sora said translating these themselves felt unsafe -- they would be
        inventing vocabulary they do not own, and a disagreement with the
        English would leave nobody able to say which was right. The fix is not
        for them to be braver: iriguchi owns the meaning, so iriguchi writes
        both and the disagreement cannot arise.
        """
        for entry in as_document("0.1.0")["rules"]:
            assert entry["detail_ja"].endswith("。"), entry["rule"]
            assert entry["detail_ja"] != entry["detail"], entry["rule"]

    def test_the_open_namespaces_carry_both_too(self) -> None:
        for entry in as_document("0.1.0")["open_namespaces"]:
            assert entry["detail_ja"].endswith("。"), entry["prefix"]

    def test_no_other_language_is_offered(self) -> None:
        """**French is deliberately absent**, and this is the test that keeps it
        so until somebody who can check the wording writes it.

        Shipping a French sentence nobody here could verify would be exactly the
        invented vocabulary Sora was right to avoid, one level further from
        anyone able to catch it. Japanese is authored, not translated: this
        project is written in Japanese, about Japanese prompts.
        """
        offered = {key for entry in as_document("0.1.0")["rules"] for key in entry}
        assert offered == {"rule", "source", "detail", "detail_ja"}, offered

    def test_the_open_namespaces_are_declared_and_explained(self) -> None:
        """The half of Sora's acceptance condition that cannot hold, stated in
        the document rather than left for them to discover.

        `presidio.person` is `f"presidio.{entity_type}"` from whatever the
        caller's analyzer returned; iriguchi never sees the list of possible
        entity types and could not enumerate it without importing the thing it
        refuses to import.
        """
        namespaces = as_document("0.1.0")["open_namespaces"]
        assert {n["prefix"] for n in namespaces} == {"presidio.", "mamori."}
        assert all(len(n["detail"].split()) >= 10 for n in namespaces)

    def test_no_open_namespace_overlaps_the_closed_set(self) -> None:
        """If they did, a consumer could not tell which half to trust."""
        for prefix, *_ in OPEN_NAMESPACES:
            assert not any(rule.startswith(prefix) for rule in CATALOGUE), prefix


class TestADecisionSaysNothingAboutWhoseItIs:
    """Sora's R8, pinned rather than answered in prose.

    Sora runs profiles -- several people on one machine -- and asked iriguchi to
    confirm it will not grow a field saying whose prompt this was. Their reason
    is the right one and it is iriguchi's too: **the judgement is about what a
    string contains, and whose string it is cannot help decide that.** An owner
    field would be a fact about a person travelling in a document whose whole
    argument is that it carries nothing about the prompt.

    A one-line answer would age. This does not.
    """

    IDENTITY = ("owner", "profile", "user", "account", "who", "subject", "actor", "session")

    def test_the_frozen_schema_has_no_identity_field(self) -> None:
        from iriguchi.interfaces.contract import schema

        def walk(node: object, path: str = "") -> list[str]:
            found: list[str] = []
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "properties" and isinstance(value, dict):
                        found += [
                            f"{path}.{name}" for name in value if name.lower() in self.IDENTITY
                        ]
                    found += walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    found += walk(value, f"{path}[{index}]")
            return found

        assert walk(schema()) == []

    def test_and_it_could_not_grow_one_quietly(self) -> None:
        """`additionalProperties: false` everywhere, so a field added without a
        version bump is refused by the schema rather than accepted by consumers
        who happen not to read it."""
        from iriguchi.interfaces.contract import schema

        def objects(node: object) -> list[dict[str, object]]:
            if isinstance(node, dict):
                here = [node] if node.get("type") == "object" else []
                return here + [o for v in node.values() for o in objects(v)]
            if isinstance(node, list):
                return [o for v in node for o in objects(v)]
            return []

        assert all(o.get("additionalProperties") is False for o in objects(schema()))

    def test_the_router_is_never_given_an_identity_to_carry(self) -> None:
        """Structural. `route` takes a prompt and what this machine can reach;
        there is no parameter an owner could arrive through, so no future
        version can start recording one without changing this signature."""
        import inspect

        from iriguchi.application.routing import PromptRouter

        parameters = set(inspect.signature(PromptRouter.route).parameters)
        assert parameters == {"self", "text", "available"}

    def test_nor_is_the_public_entry_point(self) -> None:
        import inspect

        import iriguchi

        parameters = set(inspect.signature(iriguchi.route).parameters)
        assert not parameters & set(self.IDENTITY), parameters
