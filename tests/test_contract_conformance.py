"""Is the reader as strict as the contract it says it enforces?

It was not. `MamoriChannel._read` accepted eight of nine records that mamori's
published schema rejects, including the one the contract exists to prevent: a
document declaring the plain contract while listing surrogate-protected values,
which this consumer read as a complete enumeration of one placeholder.

ADR-0013 says every disagreement with the contract is a refusal. **A consumer
that meets some obligations is a consumer that has not read the contract** --
its own words, and it was the consumer being described.

Two halves here, and the second is the one that lasts.

The first is behavioural: feed the reader documents the schema rejects and
require a refusal for each.

The second is that `REQUIRED`, `PERMITTED` and `PLACEHOLDER_KEYS` are **hand-
written from reading the schema**, because iriguchi ships no JSON Schema
validator and will not acquire one for this. Hand-written constants describing
somebody else's document are exactly what tsumugi got wrong today -- their
`KNOWN_FIELDS` was wrong in both directions the moment anything compared it to
the schema: four fields missing and one invented at the top level that actually
lives nested. So these are compared to the real file, which ships inside
mamori's wheel, in both directions.

That comparison only runs where mamori is installed, which is the seam job.
Elsewhere it skips, and the behavioural half still runs because it needs no
mamori at all -- the records are dictionaries.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from iriguchi.errors import EscalationRefusedError
from iriguchi.infrastructure.channels.mamori_channel import (
    CONTRACT,
    PERMITTED,
    PLACEHOLDER_KEYS,
    REQUIRED,
    MamoriChannel,
)
from iriguchi.infrastructure.scanners.mamori_scanner import SiblingState, mamori_state

_STATE, _DETAIL = mamori_state()

VALID: dict[str, Any] = {
    "contract": CONTRACT,
    "by": "mamori/0.27.0",
    "scope": "session-651be71fb1e1",
    "reversible": True,
    "mode": "placeholder",
    "placeholders": [{"token": "<PERSON_001>", "kind": "PERSON"}],
    "protected": [],
    "masked": [],
}


def _reader() -> MamoriChannel:
    """Without the install check. `_read` touches no mamori code."""
    return MamoriChannel.__new__(MamoriChannel)


class TestTheReaderRefusesWhatTheSchemaRejects:
    def test_a_valid_record_is_read(self) -> None:
        """The floor. A test suite of refusals passes on a reader that refuses
        everything, and that reader is useless rather than strict."""
        assert len(_reader()._read(dict(VALID))) == 1

    def test_the_optional_fields_are_still_optional(self) -> None:
        """`recall` and `policy_hash` are permitted and not required. Refusing
        them would be strictness pointed at the contract instead of at a
        document -- the failure mode of every rule written in a hurry."""
        record = {**VALID, "recall": "balanced", "policy_hash": "sha256:" + "a" * 64}
        assert len(_reader()._read(record)) == 1

    @pytest.mark.parametrize("key", sorted(REQUIRED - {"contract"}))
    def test_a_missing_required_field_is_refused(self, key: str) -> None:
        record = {k: v for k, v in VALID.items() if k != key}
        with pytest.raises(EscalationRefusedError, match="requires"):
            _reader()._read(record)

    def test_an_unknown_key_is_refused(self) -> None:
        """`additionalProperties: false`. An unexpected key is not a newer
        producer being helpful."""
        with pytest.raises(EscalationRefusedError, match="additionalProperties"):
            _reader()._read({**VALID, "note": "anything at all"})

    def test_the_plain_contract_carrying_surrogates_is_refused(self) -> None:
        """The one the contract identifier exists for.

        This record was **accepted**, and reported one finding while silently
        dropping three surrogate-protected values. Reading half a record as a
        whole one, which is the sentence ADR-0013 quotes the schema about.
        """
        record = {**VALID, "protected": [{"kind": "PERSON", "count": 3}]}
        with pytest.raises(EscalationRefusedError, match="half record"):
            _reader()._read(record)

    @pytest.mark.parametrize(
        "entry",
        [
            {"kind": "PERSON"},
            {"token": "<PERSON_001>"},
            {"token": "<PERSON_001>", "kind": "PERSON", "value": "a real name"},
        ],
        ids=["no token", "no kind", "an extra field that could hold a value"],
    )
    def test_a_malformed_placeholder_entry_is_refused(self, entry: dict[str, str]) -> None:
        with pytest.raises(EscalationRefusedError, match="placeholders"):
            _reader()._read({**VALID, "placeholders": [entry]})

    def test_the_surrogate_contract_is_refused(self) -> None:
        """Through the check already present, which is the design."""
        with pytest.raises(EscalationRefusedError, match="contract"):
            _reader()._read({**VALID, "contract": f"{CONTRACT}+surrogate"})


@pytest.mark.skipif(
    _STATE is SiblingState.ABSENT,
    reason="mamori is not installed; the schema ships in its wheel",
)
class TestTheHandWrittenConstantsMatchTheRealSchema:
    """tsumugi's `KNOWN_FIELDS` was wrong in both directions immediately.

    Both directions here too: a field the schema has and these constants do not
    is a check that will not fire, and one these have and the schema does not is
    a refusal of a valid document.
    """

    @staticmethod
    def _schema() -> dict[str, Any]:
        import importlib.resources

        assert _STATE is SiblingState.AVAILABLE, _DETAIL
        path = importlib.resources.files("mamori").joinpath("schemas/protection-scope-1.json")
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def test_required_is_exactly_the_schemas_required(self) -> None:
        assert set(self._schema()["required"]) == REQUIRED

    def test_permitted_is_exactly_the_schemas_properties(self) -> None:
        assert set(self._schema()["properties"]) == PERMITTED

    def test_required_is_a_subset_of_permitted(self) -> None:
        """Otherwise a document could be required to hold a key it may not."""
        assert REQUIRED <= PERMITTED

    def test_the_placeholder_shape_is_the_schemas(self) -> None:
        items = self._schema()["properties"]["placeholders"]["items"]
        assert PLACEHOLDER_KEYS == set(items["properties"]) == set(items["required"])
        assert items["additionalProperties"] is False

    def test_the_contract_this_build_reads_is_one_the_schema_names(self) -> None:
        assert CONTRACT in self._schema()["properties"]["contract"]["enum"]

    def test_the_surrogate_contract_is_the_one_being_refused(self) -> None:
        """If mamori renamed it, the refusal above would be testing a string
        nothing produces -- passing while protecting nothing."""
        enum = set(self._schema()["properties"]["contract"]["enum"])
        assert enum - {CONTRACT} == {f"{CONTRACT}+surrogate"}

    def test_the_plain_contract_still_forbids_surrogates(self) -> None:
        """The `if`/`then` iriguchi restates by hand. If mamori relaxed it, the
        hand-written version would be stricter than the contract and would
        refuse documents mamori considers valid."""
        rules = self._schema()["allOf"]
        plain = [r for r in rules if r["if"]["properties"]["contract"]["const"] == CONTRACT]
        assert len(plain) == 1
        assert plain[0]["then"]["properties"]["protected"]["maxItems"] == 0
