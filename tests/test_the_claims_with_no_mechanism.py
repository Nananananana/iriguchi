"""Four structural claims, and the two that were only sentences.

`AGENTS.md` and the README make four claims about what `src/` cannot do. Two of
them had a mechanism behind them and two were prose:

    import logging in src/          **0**   -- nothing checked it
    a write path in src/            **0**   -- nothing checked it
    modules permitted to send        1      `.importlinter` and an AST test
    domain imports                stdlib 6  an AST test with an allow-list

mamori found the same split in themselves and put it exactly right: **a count
with no check is the fact of the day it was written.** Their `import logging` was
zero, said so in the README, and was defended by nothing; theirs went silently
false the moment somebody added one.

**The write-path claim is the strongest thing iriguchi says about itself** — a
gatekeeper that keeps no record — and it was the less defended of the two. One
`write_text` in a future adapter turns the README into a false statement with no
test between.

## Why the AST and not a grep

A grep for `write_text` matches this docstring. Every check in this file walks
the syntax tree, so the population is calls and imports rather than lines, and
an explanation cannot satisfy the rule it explains. That mistake was made five
times in one week here.

## The last class, and why the exemption is pinned rather than assumed

`route --explain` cannot leak a value because it never prints one — rule ids,
spans and types only. mamori's move today was to stop treating that as a reason
to skip the check and **make the reason itself the check**: pin *no value comes
out*, and the exemption stops being an argument somebody has to remember.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path
from typing import ClassVar

import pytest

import iriguchi
from iriguchi.interfaces.cli import main as cli

PACKAGE_ROOT = Path(iriguchi.__file__).parent
SOURCES = sorted(PACKAGE_ROOT.rglob("*.py"))

assert len(SOURCES) >= 20, (
    f"the package glob found {len(SOURCES)} files. A check that looked at "
    f"nothing reports the same success as one that looked at everything."
)

#: Names whose call means something left this process for a filesystem. Read
#: paths are deliberately absent: `evaluation/dataset.py` reads the corpus, and
#: reading a file that shipped in the wheel is not a record of anybody's prompt.
WRITING = frozenset(
    {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "writelines",
        "mkdir",
        "touch",
        "unlink",
        "rename",
        "makedirs",
        "NamedTemporaryFile",
        "TemporaryFile",
        "mkstemp",
    }
)

#: Names that write only when they belong to something. `os.remove` writes;
#: `list.remove` does not. `Path.replace` writes; `str.replace` does not, and
#: both are called here -- `mamori_channel.py` and `main.py` each tripped the
#: first draft of this check on `str.replace`.
#:
#: **A check that fires on `str.replace` gets a `noqa` and then protects
#: nothing**, so these need their owner named.
QUALIFIED = {("os", "remove"), ("os", "rename"), ("os", "replace"), ("json", "dump")}

#: What this therefore does not catch, said rather than left to be discovered:
#: a `Path` bound to a variable and then `.replace`d or `.remove`d. Nothing in
#: `src/` binds a `Path` to anything but `DATA_DIR`, and the write-path claim is
#: also carried by `no_module_imports_a_way_to_record` -- but this is a gap, not
#: an absence of one.
UNCAUGHT = "a Path in a variable, then .replace() or .remove()"


#: Modules whose presence means a record could be kept, whatever is done with
#: them. `logging` is the one the README names; the rest are the same promise
#: spelled differently.
RECORDING = frozenset({"logging", "shelve", "pickle", "dbm", "csv", "tempfile", "shutil"})


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imported(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def _writes(path: Path) -> set[str]:
    """Every call in this module that puts something on a filesystem.

    A tree walk rather than a grep: a docstring naming `write_text` must not
    satisfy the rule it explains, and this file's own prose names most of
    `WRITING`.

    Qualified names are matched with their owner, because `str.replace` and
    `Path.replace` share a spelling and only one of them writes.
    """
    found: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            if target.id in WRITING:
                found.add(target.id)
        elif isinstance(target, ast.Attribute):
            owner = target.value
            if isinstance(owner, ast.Name) and (owner.id, target.attr) in QUALIFIED:
                found.add(f"{owner.id}.{target.attr}")
            elif target.attr in WRITING:
                found.add(target.attr)
    return found


def _calls_anything_named(path: Path, name: str) -> bool:
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute) and target.attr == name:
                return True
            if isinstance(target, ast.Name) and target.id == name:
                return True
    return False


IDS = [str(p.relative_to(PACKAGE_ROOT)) for p in SOURCES]


class TestNothingKeepsARecord:
    """The claim iriguchi makes most strongly about itself, checked.

    A router that sees every prompt and writes none of them down is the whole
    argument for running it. ADR-0012 says a decision inherits the
    classification of its prompt, is never written to disk and never sent; that
    is enforced here rather than reviewed.
    """

    @pytest.mark.parametrize("path", SOURCES, ids=IDS)
    def test_no_module_imports_a_way_to_record(self, path: Path) -> None:
        found = sorted(_imported(path) & RECORDING)
        assert not found, (
            f"{path.relative_to(PACKAGE_ROOT)} imports {found}. Nothing in "
            f"iriguchi keeps a record: a decision inherits the classification of "
            f"its prompt (ADR-0012), and the README says the dependency list is "
            f"the threat model. If a record is genuinely wanted, it needs an ADR "
            f"and a line here, not an import."
        )

    @pytest.mark.parametrize("path", SOURCES, ids=IDS)
    def test_no_module_writes_anything(self, path: Path) -> None:
        found = sorted(_writes(path))
        assert not found, (
            f"{path.relative_to(PACKAGE_ROOT)} calls {found}. `src/` reads the "
            f"corpus that shipped in the wheel and writes nothing at all -- there "
            f"is no `--log-file`, and that is the point rather than an omission."
        )

    def test_reading_is_still_allowed_and_still_happens(self) -> None:
        """The other half. A rule that forbade reading too would pass on a
        package that had stopped loading its own corpus, and this test would
        have nothing to say about it."""
        readers = [p for p in SOURCES if _calls_anything_named(p, "read_text")]
        assert readers, "nothing reads the corpus any more, so this file is guarding a ghost"


class TestTheReadmeStillMakesTheClaim:
    """A check that outlives its claim leaves two sentences disagreeing.

    mamori's addition, and it points the other way from everything else here:
    the risk is not only that the claim loses its check, but that the check
    loses its claim and goes on defending a promise the documentation stopped
    making.
    """

    @staticmethod
    def _readme() -> str:
        return (PACKAGE_ROOT.parent.parent / "README.md").read_text(encoding="utf-8")

    def test_the_dependency_promise_is_still_written_down(self) -> None:
        assert "Zero runtime dependencies" in self._readme()

    def test_the_never_printed_value_promise_is_still_written_down(self) -> None:
        assert "Never the matched values themselves" in self._readme()


class TestTheGroundsForTheExemption:
    """The exemption was real and I had stated it too widely.

    #42 said `route --explain` is *structurally incapable* of printing a
    character it did not choose, and used that to explain why the `cp932` crash
    could not reach it. **That is false for an outbound route**, which prints
    `would leave` -- the protected text, verbatim when nothing needed
    protecting. The test that was supposed to cover it set only
    `IRIGUCHI_LOCAL=1`, so it never took that branch.

    The true rule is narrower and still worth having:

        reasons, findings, signals   **never carry a value**
        `would leave`                **carries the text on purpose**

    The second is the feature -- showing what would be sent is the whole of
    `--dry-run` -- which is why the `cp932` fix routes it through
    `print_content` rather than suppressing it. Both halves are asserted here,
    because a leak "fixed" by deleting the feature would pass the first alone.
    """

    #: One of each kind a scanner finds. The `é` is deliberate: it is absent
    #: from `cp932` **and** it is a value, so a single mistake would break two
    #: promises at once.
    VALUES: ClassVar[dict[str, str]] = {
        "an email": "tanaka@example.com",
        "a japanese name": "田中太郎",
        "an accented name": "Zoé Dupont",
        "a credential": "correcthorsebattery",
        "a card number": "4111111111111111",
    }

    @staticmethod
    def _explanation(printed: str) -> str:
        """Everything above `would leave`, which is the part that must be clean.

        Splitting rather than searching the whole output, because the section
        below it is *supposed* to contain the text and a whole-output assertion
        would have to be either wrong or disabled.
        """
        marker = "would leave"
        return printed[: printed.index(marker)] if marker in printed else printed

    @pytest.mark.parametrize("value", VALUES.values(), ids=list(VALUES))
    @pytest.mark.parametrize("argv", [["route"], ["route", "--explain"]], ids=["plain", "explain"])
    def test_the_reasons_never_carry_the_value(
        self, value: str, argv: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        cli.main([*argv, f"Compare these and prove the lemma. Contact {value}."], out)
        printed = out.getvalue()
        assert "route" in printed and "sensitivity" in printed, "the command printed nothing"
        assert value not in self._explanation(printed), (
            f"{value!r} reached the explanation. Messages carry rule ids, spans "
            f"and types, never a matched value."
        )

    def test_the_outbound_branch_is_actually_reached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The assertion above proves nothing about `would leave` unless the
        route is outbound. #42's version of this test set `IRIGUCHI_LOCAL` only,
        so it never took the branch it was written to clear."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        cli.main(["route", "--explain", "Compare these and prove the lemma, step by step."], out)
        assert "would leave" in out.getvalue()

    def test_would_leave_does_show_the_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The half that stops the other half being satisfied by deletion.

        `--dry-run` exists to show what would be sent. A version that printed
        nothing there would pass every absence assertion in this class and would
        have removed the only reason the command exists.
        """
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        out = io.StringIO()
        prompt = "Compare these and prove the lemma, step by step."
        cli.main(["route", "--explain", prompt], out)
        printed = out.getvalue()
        below = printed[printed.index("would leave") :]
        assert "prove the lemma" in below, "nothing was shown as leaving"

    def test_a_span_is_printed_instead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The explanation stays useful. A command printing nothing at all
        would satisfy every absence assertion above."""
        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        out = io.StringIO()
        cli.main(["route", "--explain", "Contact tanaka@example.com about the proof."], out)
        printed = out.getvalue()
        assert "sensitivity" in printed
        assert any(character.isdigit() for character in printed), "no offsets were reported"
