"""The document iriguchi produces, checked against the schema it publishes.

tsumugi shipped a reference loader that **accepted a package their own published
schema rejects** — `additionalProperties: false` everywhere, an ADR saying v1
was closed, and the loader let extra fields through silently. iriguchi found the
consuming half of the same defect in its own mamori reader: it accepted eight of
nine documents mamori's schema refuses.

This is the producing half, closed before it can open. Every document
`route --json` can emit is validated against `schemas/routing-decision-1.json`
by a real JSON Schema validator, over prompts chosen to reach every branch of
the document.

## Why `jsonschema` is a dependency here and `cosmic-ray` was not

Both are development-only and one was refused three hours ago for adding 726
lines to `uv.lock`. The difference is not size — `jsonschema` adds 154 — it is
**what the dependency is for**. `cosmic-ray` was a convenience that two hundred
lines of standard library replaced. This is an obligation to somebody
downstream: a published schema that nothing validates against is a promise with
no check, and hand-rolling a JSON Schema validator to avoid a dependency would
mean the promise is checked by a validator nobody else uses.

Nothing ships with it. `pip install iriguchi` still pulls nothing, and the job
that proves that is unchanged.
"""

from __future__ import annotations

import io
import json
from typing import Any, ClassVar

import pytest
from jsonschema import Draft202012Validator

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.complexity import Thresholds
from iriguchi.domain.destination import Destination
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS
from iriguchi.interfaces.cli import main as cli
from iriguchi.interfaces.contract import CONTRACT, as_document, schema

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})
NOTHING: frozenset[Destination] = frozenset()

#: Prompts chosen to reach every branch of the document, not to look varied.
#: A validation suite over five similar prompts validates one shape five times.
REACHING = {
    "a clean simple one": ("Summarise this article in three lines.", BOTH),
    "one that escalates": (
        "Refactor this module and explain why, step by step, with alternatives considered.",
        BOTH,
    ),
    "one with findings": ("田中太郎さんに tanaka@example.com で連絡してください", BOTH),
    "findings and complexity together": (
        "Contact tanaka@example.com and prove the lemma, step by step, comparing both.",
        BOTH,
    ),
    "a refusal": ("Summarise this.", NOTHING),
    "empty": ("", BOTH),
    "one with no ascii at all": ("これを三行で要約してください。", BOTH),
}


def _decide(prompt: str, available: frozenset[Destination]) -> dict[str, Any]:
    router = PromptRouter(scanner=SCANNERS.build("fallback"), estimator=ESTIMATORS.build("rules"))
    return as_document(router.route(prompt, available), Thresholds())


class TestTheSchemaItself:
    def test_it_is_a_valid_json_schema(self) -> None:
        """Before anything is validated against it. A schema with a typo in a
        keyword validates everything and says nothing, which is the same shape
        as a check that cannot fail."""
        Draft202012Validator.check_schema(schema())

    def test_it_ships_in_the_wheel(self) -> None:
        """Read through `importlib.resources`, so this fails if the file is in
        the repository and not in the package -- the trap three siblings were
        measured in for `py.typed`."""
        assert schema()["title"] == CONTRACT

    def test_it_closes_every_object(self) -> None:
        """`additionalProperties: false` everywhere, and v1 is frozen. A schema
        that closes the top level and leaves a nested object open is closed in
        the place nobody adds fields to."""
        opened: list[str] = []

        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object" and node.get("additionalProperties") is not False:
                    opened.append(path or "<root>")
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(schema(), "")
        assert not opened, f"{opened} accept unknown fields"


class TestEveryPublishedNumberSaysWhatItIs:
    """mamori's warning, turned on what iriguchi had just shipped.

        The most dangerous thing in a compatibility layer is not the field you
        cannot fill. It is the field you filled with something it does not mean.

    They found it as `analysis_explanation` holding a dict Presidio would read
    as an `AnalysisExplanation`. **Here it arrives as a number.** `score` and
    `weight` are in [0,1], which is the shape of a probability, and neither is
    one: the weights are assigned by hand and nothing has calibrated them
    against an outcome.

    A reader coming from Presidio -- where `RecognizerResult.score` genuinely
    **is** a confidence -- will read `0.56` as *56% sure* unless the document
    says otherwise. And this project refuses a confidence on findings for
    exactly that reason: *a confidence would become a threshold, and a threshold
    is a score.* Refusing it in the domain and publishing an uncaveated one in
    the contract is the same mistake with a longer reach.
    """

    @staticmethod
    def _numbers(node: object, path: str = "") -> list[tuple[str, dict[str, Any]]]:
        found: list[tuple[str, dict[str, Any]]] = []
        if isinstance(node, dict):
            if node.get("type") in {"number", "integer"}:
                found.append((path, node))
            for key, value in node.items():
                found.extend(TestEveryPublishedNumberSaysWhatItIs._numbers(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.extend(
                    TestEveryPublishedNumberSaysWhatItIs._numbers(value, f"{path}[{index}]")
                )
        return found

    def test_there_are_numbers_to_check(self) -> None:
        """A floor. An empty sweep passes every assertion below."""
        assert len(self._numbers(schema())) >= 5

    def test_every_number_is_described(self) -> None:
        """An undescribed number in a published contract is an invitation to
        guess, and the guess will be *confidence*."""
        undescribed = [
            path for path, node in self._numbers(schema()) if not node.get("description")
        ]
        assert not undescribed, f"{undescribed} are numbers a consumer has to guess the meaning of"

    @pytest.mark.parametrize("field", ["score", "weight"])
    def test_the_ones_shaped_like_a_probability_deny_being_one(self, field: str) -> None:
        """Both live in [0,1] and neither is a confidence. Saying so is the
        whole difference between a number and a number somebody can misuse."""
        matching = [
            node
            for path, node in self._numbers(schema())
            if path.endswith(f".{field}") and node.get("maximum") == 1
        ]
        assert matching, f"no [0,1] `{field}` found; this test is guarding nothing"
        for node in matching:
            assert "not a confidence" in node["description"].lower()

    def test_a_finding_still_carries_no_score(self) -> None:
        """The domain refuses one. The contract must not quietly add it back to
        look more like a `RecognizerResult`."""
        finding = schema()["$defs"]["finding"]
        assert "score" not in finding["properties"]
        assert "no score here" in finding["description"].lower()


class TestEveryDocumentValidates:
    @pytest.mark.parametrize("prompt,available", REACHING.values(), ids=list(REACHING))
    def test_it_matches_the_published_schema(
        self, prompt: str, available: frozenset[Destination]
    ) -> None:
        Draft202012Validator(schema()).validate(_decide(prompt, available))

    def test_the_cases_between_them_reach_every_branch(self) -> None:
        """A suite of documents that all look alike validates one shape many
        times. This asserts the fixtures actually differ where it matters."""
        documents = [_decide(prompt, available) for prompt, available in REACHING.values()]
        assert {d["route"] for d in documents} >= {"local", "external", "refused"}
        assert any(d["sensitivity"]["findings"] for d in documents)
        assert any(not d["sensitivity"]["findings"] for d in documents)
        assert any(d["removed"] for d in documents)
        assert any(d["complexity"]["signals"] for d in documents)

    def test_thresholds_are_omitted_rather_than_defaulted_when_not_recorded(self) -> None:
        """Absent means *not recorded*, not *the defaults applied*. mamori draws
        the same distinction for `recall`, and a field that reads as a default
        when it is really a silence is a field that lies quietly."""
        router = PromptRouter(
            scanner=SCANNERS.build("fallback"), estimator=ESTIMATORS.build("rules")
        )
        document = as_document(router.route("hello", BOTH))
        assert "thresholds" not in document
        Draft202012Validator(schema()).validate(document)


class TestWhatTheDocumentMustNotCarry:
    """The reason publishing a decision does not contradict ADR-0012.

    A document holding rule ids, spans and arithmetic is not the prompt it
    describes. A document holding one word of the prompt is.
    """

    PLANTED: ClassVar[dict[str, str]] = {
        "an email": "tanaka@example.com",
        "a japanese name": "田中太郎",
        "an accented name": "Zoé Dupont",
        "a credential": "correcthorsebattery",
        "a card number": "4111111111111111",
        "an ordinary word from the prompt": "pomegranate",
    }

    @pytest.mark.parametrize("value", PLANTED.values(), ids=list(PLANTED))
    def test_no_value_from_the_prompt_reaches_the_document(self, value: str) -> None:
        document = _decide(f"Prove the lemma about {value}, step by step.", BOTH)
        assert value not in json.dumps(document, ensure_ascii=False)

    @pytest.mark.parametrize("value", PLANTED.values(), ids=list(PLANTED))
    def test_nor_through_the_command(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Through the CLI as well as the function, because the command is what
        somebody pipes into a file."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        cli.main(["route", "--json", f"Prove the lemma about {value}, step by step."], out)
        printed = out.getvalue()
        assert json.loads(printed)["contract"] == CONTRACT, "the document did not parse"
        assert value not in printed


class TestWhatAConsumerReadsFirst:
    def test_the_contract_identifier_is_the_first_key(self) -> None:
        """JSON objects are unordered by spec and a person scanning a terminal
        is not. Sorting the keys put `by` first, which is the field a consumer
        should read *after* deciding it understands the document at all."""
        document = _decide("hello", BOTH)
        assert next(iter(document)) == "contract"

    def test_the_identifier_carries_the_state(self) -> None:
        """akashi's finding, applied to what iriguchi produces: the version is
        on the field read first, not on a summary beside it."""
        assert schema()["properties"]["contract"]["const"] == CONTRACT
        assert "contract" in schema()["required"]

    def test_the_producer_version_is_recorded(self) -> None:
        """A decision cannot be reproduced without knowing which rules and
        thresholds were in force."""
        assert _decide("hello", BOTH)["by"].startswith("iriguchi/")


class TestItIsStable:
    def test_the_same_prompt_produces_the_same_bytes(self) -> None:
        """So a diff between two documents is a difference in the decision and
        not in a dict's iteration order."""
        first = json.dumps(_decide("Prove the lemma, step by step.", BOTH))
        second = json.dumps(_decide("Prove the lemma, step by step.", BOTH))
        assert first == second

    def test_the_schema_command_prints_the_shipped_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("IRIGUCHI_LOCAL", raising=False)
        out = io.StringIO()
        assert cli.main(["schema"], out) == cli.EXIT_OK
        assert json.loads(out.getvalue()) == schema()

    def test_a_refusal_still_exits_two_in_json_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The exit code is the same contract as in prose mode. A script that
        switched to `--json` and lost the distinction between "no" and "broken"
        would retry a refusal forever."""
        for key in ("IRIGUCHI_LOCAL", "IRIGUCHI_EXTERNAL"):
            monkeypatch.delenv(key, raising=False)
        out = io.StringIO()
        assert cli.main(["route", "--json", "hello"], out) == cli.EXIT_REFUSED
        assert json.loads(out.getvalue())["route"] == "refused"
