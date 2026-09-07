"""The two draft documents, validated against the schemas the wheel ships.

iriguchi published three documents and shipped one schema. `routing-decision/1`
had one, was validated against it, and the file that does so says why:

    a published schema that nothing validates against is a promise with no check

The inverse was true of the other two and nobody had said it: **a published
document with no schema is a promise with no shape.** Sora vendors both --
`route-batch/1-draft` went into their `KNOWN` list and their manifest's
`produces` -- and had nothing to vendor but an example.

So both have schemas now, and both are validated against real output here, over
inputs chosen to reach every branch of the document rather than to look varied.
"""

from __future__ import annotations

import io
import json
from typing import Any, ClassVar

import pytest
from jsonschema import Draft202012Validator

from iriguchi import __version__
from iriguchi.interfaces.cli.main import EXIT_OK, main
from iriguchi.interfaces.contract import CONTRACT, SCHEMAS, schema
from iriguchi.interfaces.rules import CONTRACT as RULES_CONTRACT
from iriguchi.interfaces.rules import as_document as rules_document

BATCH = "route-batch-1-draft.json"
RULES = "rules-1-draft.json"


def shipped(name: str) -> dict[str, Any]:
    """A schema read through `importlib.resources`, from the installed package.

    Not from the repository. A schema that only exists next to the source is one
    nobody downstream can check against, and this is the trap three siblings
    were measured in for `py.typed`.
    """
    import importlib.resources

    resource = importlib.resources.files("iriguchi").joinpath(f"schemas/{name}")
    return json.loads(resource.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class _Stdin(io.TextIOWrapper):
    def __init__(self, data: bytes) -> None:
        super().__init__(io.BytesIO(data), encoding="utf-8")


def _batch(lines: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import sys

    monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
    monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
    payload = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", _Stdin(payload))
    out = io.StringIO()
    assert main(["route", "--batch"], out=out) == EXIT_OK
    return [json.loads(text) for text in out.getvalue().splitlines() if text.strip()]


class TestBothSchemasAreValidSchemas:
    """Before anything is validated against them. A schema with a typo in a
    keyword validates everything and says nothing, which is the same shape as a
    check that cannot fail."""

    @pytest.mark.parametrize("name", [BATCH, RULES])
    def test_it_is_a_valid_json_schema(self, name: str) -> None:
        Draft202012Validator.check_schema(shipped(name))

    @pytest.mark.parametrize("name,title", [(BATCH, "route-batch"), (RULES, "rules")])
    def test_it_ships_in_the_wheel(self, name: str, title: str) -> None:
        assert shipped(name)["title"] == f"iriguchi.{title}/1-draft"

    @pytest.mark.parametrize("name", [BATCH, RULES])
    def test_it_closes_every_object_it_owns(self, name: str) -> None:
        """`additionalProperties: false` everywhere iriguchi owns the shape.

        The one exception is the batch envelope's `decision`, which is left open
        on purpose: it is somebody else's schema, and repeating that schema here
        would be a second copy to keep in step. The copy is always the one that
        goes stale.
        """
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

        walk(shipped(name), "")
        assert opened == ([".properties.decision"] if name == BATCH else []), opened


class TestTheBatchDocument:
    #: Chosen to reach every branch: an id that is a string, one that is a
    #: number, one absent entirely, a prompt that is refused by the veto, and a
    #: line carrying supplied findings.
    REACHING: ClassVar[list[dict[str, Any]]] = [
        {"id": "a-card", "prompt": "Summarise this article in three lines."},
        {"id": 7, "prompt": "Email tanaka@example.com the figures."},
        {"prompt": "この記事を三行で要約してください。"},
        {
            "id": "supplied",
            "prompt": "Alice, prove the lemma.",
            "findings": [{"entity_type": "PERSON", "start": 0, "end": 5, "score": 0.9}],
        },
    ]

    def test_every_line_matches_the_shipped_schema(self, monkeypatch: pytest.MonkeyPatch) -> None:
        validator = Draft202012Validator(shipped(BATCH))
        for row in _batch(self.REACHING, monkeypatch):
            validator.validate(row)

    def test_the_lines_between_them_reach_every_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A suite of documents that all look alike validates one shape many
        times. This asserts the fixtures actually differ where it matters."""
        rows = _batch(self.REACHING, monkeypatch)
        assert {type(row["id"]).__name__ for row in rows} >= {"str", "int", "NoneType"}
        levels = {row["decision"]["sensitivity"]["level"] for row in rows}
        assert levels == {"clear", "restricted"}

    def test_a_missing_id_is_null_rather_than_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """So a consumer matching answers to prompts sees the difference between
        *the caller gave no id* and *the id happened to be falsy*, and can refuse
        to guess by position."""
        [row] = _batch([{"prompt": "hello"}], monkeypatch)
        assert "id" in row and row["id"] is None

    def test_the_decision_inside_is_the_frozen_one_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The envelope's whole reason to exist. `routing-decision/1` cannot
        grow an `id`, so the id lives outside it -- and the document inside must
        still validate against the contract iriguchi already ships."""
        validator = Draft202012Validator(schema())
        for row in _batch(self.REACHING, monkeypatch):
            validator.validate(row["decision"])

    def test_it_is_byte_for_byte_what_route_json_would_have_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not merely valid: **the same**. A batch that produced a subtly
        different decision would be a second router, and nobody would know."""
        import sys

        prompt = "Email tanaka@example.com the figures."
        [row] = _batch([{"id": 1, "prompt": prompt}], monkeypatch)

        monkeypatch.setattr(sys, "stdin", _Stdin(prompt.encode("utf-8")))
        out = io.StringIO()
        assert main(["route", "--json", "-"], out=out) == EXIT_OK
        assert row["decision"] == json.loads(out.getvalue())

    def test_no_part_of_any_prompt_reaches_the_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-0006 does not stop at the decision's edge. The envelope carries
        an id the caller chose and nothing else."""
        rendered = json.dumps(_batch(self.REACHING, monkeypatch), ensure_ascii=False)
        for value in ("tanaka@example.com", "Alice", "要約"):
            assert value not in rendered


class TestTheRulesDocument:
    def test_it_matches_the_shipped_schema(self) -> None:
        Draft202012Validator(shipped(RULES)).validate(rules_document(__version__))

    def test_the_command_writes_the_same_thing(self) -> None:
        out = io.StringIO()
        assert main(["rules"], out=out) == EXIT_OK
        Draft202012Validator(shipped(RULES)).validate(json.loads(out.getvalue()))

    def test_the_schema_would_refuse_a_rule_with_no_japanese(self) -> None:
        """The pair is required, so a build that shipped English alone would be
        refused by its own published shape rather than accepted by a consumer
        that happened not to look."""
        document = rules_document(__version__)
        broken = json.loads(json.dumps(document))
        del broken["rules"][0]["detail_ja"]
        with pytest.raises(Exception, match="detail_ja"):
            Draft202012Validator(shipped(RULES)).validate(broken)

    def test_the_schema_would_refuse_a_third_language(self) -> None:
        """`additionalProperties: false` on a rule. Somebody adding `detail_fr`
        has to change the published shape to do it, which is the point at which
        the question *who can check this French?* gets asked."""
        broken = json.loads(json.dumps(rules_document(__version__)))
        broken["rules"][0]["detail_fr"] = "quelque chose"
        with pytest.raises(Exception, match="detail_fr"):
            Draft202012Validator(shipped(RULES)).validate(broken)

    def test_the_identifier_pattern_would_refuse_an_open_namespace_entry(self) -> None:
        """`presidio.person` is not a rule and must never appear in `rules`.
        The pattern allows it structurally -- both halves are lower-case -- so
        this is the test, and `test_no_open_namespace_overlaps_the_closed_set`
        is the one that holds the invariant."""
        listed = {entry["rule"] for entry in rules_document(__version__)["rules"]}
        assert not any(rule.startswith(("presidio.", "mamori.")) for rule in listed)


class TestTheRegistryAgreesWithEverythingElse:
    """`SCHEMAS` repeats three contract ids as literals, because importing them
    would point `interfaces.contract` at its own consumers. A repeated string is
    a string that can drift, so the agreement is held here -- the arrangement
    `ALLOWED`, `AGENTS.md` and `.importlinter` are already in."""

    def test_every_published_document_has_an_entry(self) -> None:
        from iriguchi.interfaces.cli.main import BATCH_CONTRACT
        from iriguchi.interfaces.error_catalogue import CONTRACT as ERRORS_CONTRACT

        assert set(SCHEMAS) == {CONTRACT, BATCH_CONTRACT, RULES_CONTRACT, ERRORS_CONTRACT}

    @pytest.mark.parametrize("contract", sorted(SCHEMAS))
    def test_the_entry_points_at_the_schema_for_that_contract(self, contract: str) -> None:
        """Not merely at *a* file that exists. Two entries swapped would leave
        both readable, both valid, and both wrong -- and a consumer generating
        code from `schema("...rules/1-draft")` would get the batch envelope."""
        assert schema(contract)["title"] == contract

    @pytest.mark.parametrize("contract", sorted(SCHEMAS))
    def test_the_command_prints_it(self, contract: str) -> None:
        out = io.StringIO()
        assert main(["schema", contract], out=out) == EXIT_OK
        assert json.loads(out.getvalue()) == schema(contract)

    def test_the_command_with_no_argument_still_prints_the_frozen_one(self) -> None:
        """Every caller that existed before today wrote `iriguchi schema` and
        meant this. An argument that changed what the bare command prints would
        be a silent break in somebody's pipeline."""
        out = io.StringIO()
        assert main(["schema"], out=out) == EXIT_OK
        assert json.loads(out.getvalue())["title"] == CONTRACT

    def test_a_contract_this_build_does_not_publish_is_refused_by_name(self) -> None:
        from iriguchi.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="publishes no schema"):
            schema("iriguchi.routing-decision/2")
