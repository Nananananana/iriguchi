"""The layering rules, enforced rather than promised.

Every document in this repository says the domain imports nothing but the
standard library, that dependencies point inwards, and that the deciding path
has no way to send. Written down, those are conventions upheld by whoever last
read `AGENTS.md`, and conventions about imports lose to autocomplete.

This walks the source with `ast` and checks them. `import-linter` checks the
same directions in CI and catches things this does not; this catches the one
rule no contract type can express -- *the domain may import the standard library
and nothing else* -- because that is a statement about everything that is not
listed rather than about a list. ADR-0010.

The `ALLOWED` table below is the authority. `AGENTS.md` describes it, and
`test_the_documented_table_names_every_layer` fails when the two drift apart.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import iriguchi

PACKAGE_ROOT = Path(iriguchi.__file__).parent
PACKAGE = "iriguchi"
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Which layers each layer may import. A layer absent from a value cannot be
#: reached from that key, whatever the import looks like.
ALLOWED: dict[str, frozenset[str]] = {
    # Pure. Stdlib only, and not all of it -- see TestTheDomainIsPure.
    "domain": frozenset(),
    # The protocols the application depends on. They speak in domain terms.
    "ports": frozenset({"domain"}),
    # Orchestration.
    "application": frozenset({"domain", "ports"}),
    # Adapters. They implement ports, and they are the only place I/O lives.
    "infrastructure": frozenset({"domain", "ports"}),
    # Measurement runs the real pipeline, so it reaches the application.
    "evaluation": frozenset({"domain", "ports", "application", "infrastructure"}),
    # The outside edge. Nothing imports it.
    "interfaces": frozenset({"domain", "ports", "application", "infrastructure", "evaluation"}),
    # Exceptions are shared by everything and import nothing.
    "errors": frozenset(),
}

#: Layers only the outermost edge may import. An adapter reaching into the
#: evaluation harness, or anything at all reaching into the CLI, is a layering
#: mistake that would otherwise surface only as a strange import cycle.
NEVER_IMPORTED = frozenset({"interfaces", "evaluation"})

#: The one layer allowed to import those, because driving them is its job.
OUTERMOST = "interfaces"


def source_files() -> Iterator[Path]:
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def layer_of(path: Path) -> str:
    """The top-level layer a file belongs to."""
    relative = path.relative_to(PACKAGE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def imported_layers(path: Path) -> set[str]:
    """Layers this file imports from, resolving relative imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    depth_to_root = len(path.relative_to(PACKAGE_ROOT).parts) - 1
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                # `from ...domain.span import X` at depth 2 -> level 3 is the
                # package root, so the module names the layer.
                if node.level - 1 == depth_to_root and node.module:
                    found.add(node.module.split(".")[0])
            elif node.module and node.module.split(".")[0] == PACKAGE:
                parts = node.module.split(".")
                if len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == PACKAGE and len(parts) > 1:
                    found.add(parts[1])
    return found


def imported_roots(path: Path) -> set[str]:
    """Top-level package names this file imports, relative imports excluded.

    Walks the whole tree rather than the module body, so an import inside a
    function -- the usual way a forbidden dependency arrives, because it looks
    local and harmless -- is seen too.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return roots


ALL_FILES = list(source_files())
FILE_IDS = [str(p.relative_to(PACKAGE_ROOT)) for p in ALL_FILES]
PACKAGE_INIT_LAYERS = {"__init__", "py"}


class TestLayering:
    def test_the_rules_cover_every_layer(self) -> None:
        """A new top-level module must be placed deliberately, not by default."""
        layers = {layer_of(path) for path in ALL_FILES} - PACKAGE_INIT_LAYERS
        unplaced = sorted(layers - set(ALLOWED))
        assert not unplaced, (
            f"no layering rule for {unplaced}. Add it to ALLOWED in this file, to the "
            "table in AGENTS.md, and to .importlinter -- in the same change."
        )

    @pytest.mark.parametrize("path", ALL_FILES, ids=FILE_IDS)
    def test_a_file_imports_only_what_its_layer_may(self, path: Path) -> None:
        layer = layer_of(path)
        if layer in PACKAGE_INIT_LAYERS:
            pytest.skip("the package root is a composition point, not a layer")
        allowed = ALLOWED.get(layer, frozenset())
        for target in imported_layers(path) - {layer, "errors"}:
            assert target in allowed, (
                f"{path.relative_to(PACKAGE_ROOT)} is in '{layer}' and imports "
                f"'{target}', which '{layer}' may not reach. Allowed: "
                f"{sorted(allowed) or 'stdlib only'}."
            )

    @pytest.mark.parametrize("path", ALL_FILES, ids=FILE_IDS)
    def test_nothing_imports_the_outer_layers(self, path: Path) -> None:
        layer = layer_of(path)
        for target in imported_layers(path):
            if target in NEVER_IMPORTED and layer not in {target, OUTERMOST}:
                pytest.fail(
                    f"{path.relative_to(PACKAGE_ROOT)} imports '{target}'. Nothing may "
                    "depend on the CLI or the evaluation harness."
                )

    def test_the_documented_table_names_every_layer(self) -> None:
        """AGENTS.md describes this file. It has to keep describing it.

        Only a presence check, deliberately: parsing the table's contents would
        make a prose edit break the build, and a document nobody dares reword
        stops being maintained. A layer that exists and is undocumented is the
        failure worth catching.
        """
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        missing = sorted(layer for layer in ALLOWED if f"`{layer}" not in agents)
        assert not missing, f"AGENTS.md's layer table does not mention {missing}"


class TestTheDomainIsPure:
    """The rule the whole design rests on. ADR-0001."""

    #: An allow-list, not a deny-list. Anything not named here is refused, so a
    #: new dependency on the standard library is a deliberate line in this file
    #: rather than something that arrives with an import somebody added at 2am.
    ALLOWED_STDLIB = frozenset(
        {
            "__future__",
            "collections",  # collections.abc, for the Iterable in a signature
            "dataclasses",
            "enum",
            "math",  # prod(), for combining complexity signals as independent evidence
            "typing",
        }
    )

    #: Named individually so that moving one out of the domain is a deliberate
    #: act with a failing test attached, rather than a refactor nobody notices.
    #: Every routing decision is in one of these.
    DECIDING_MODULES = frozenset({"policy", "sensitivity", "complexity", "decision"})

    def domain_files(self) -> list[Path]:
        return [p for p in ALL_FILES if layer_of(p) == "domain"]

    def test_there_is_a_domain_to_protect(self) -> None:
        """Guards against the whole suite passing because the glob found nothing."""
        assert len(self.domain_files()) >= 5

    def test_the_domain_imports_no_other_layer(self) -> None:
        for path in self.domain_files():
            reached = imported_layers(path) - {"domain"}
            assert not reached, f"{path.name} imports {sorted(reached)}"

    @pytest.mark.parametrize(
        "path", [p for p in ALL_FILES if layer_of(p) == "domain"], ids=lambda p: p.name
    )
    def test_the_domain_imports_only_the_named_standard_library(self, path: Path) -> None:
        for root in imported_roots(path):
            assert root in self.ALLOWED_STDLIB, (
                f"{path.name} imports {root!r}. The domain holds every routing "
                "decision and stays testable with no model, no network, no clock and "
                "no filesystem, which only works while it imports nothing but the "
                "standard library modules named in ALLOWED_STDLIB. If this is "
                "genuinely needed, either add it here deliberately or put the code in "
                "another layer."
            )

    @pytest.mark.parametrize(
        "path", [p for p in ALL_FILES if layer_of(p) == "domain"], ids=lambda p: p.name
    )
    def test_the_domain_has_no_io_no_clock_and_no_randomness(self, path: Path) -> None:
        """Named separately from the allow-list, because the reason differs.

        The allow-list keeps third-party code out. This keeps out standard
        library modules that would make a decision depend on something other
        than its inputs: a file that could have been written by anyone, a clock
        that reads differently on the second call, a random source that makes
        the same prompt route two ways.
        """
        forbidden = {
            "os": "a domain that can open a file can be told a different answer by it",
            "pathlib": "reading a file is an adapter's job",
            "io": "reading a file is an adapter's job",
            "sqlite3": "storage is an adapter's job",
            "tomllib": "configuration is read at the edge and passed in",
            "json": "parsing a document is an adapter's job",
            "argparse": "the command line is an interface's job",
            "subprocess": "nothing in the deciding path runs a program",
            "socket": "the deciding path has no way to send",
            "ssl": "the deciding path has no way to send",
            "http": "the deciding path has no way to send",
            "urllib": "the deciding path has no way to send",
            "asyncio": "the deciding path has no way to send",
            "time": "no wall clock in a decision; the same prompt decides the same way",
            "datetime": "no wall clock in a decision; time arrives through a Clock port",
            "random": "a decision is a function of its inputs",
            "secrets": "a decision is a function of its inputs",
            "uuid": "a decision is a function of its inputs",
            "tkinter": "the domain does not know a screen exists",
        }
        for root in imported_roots(path) & forbidden.keys():
            pytest.fail(f"{path.name} imports {root!r}: {forbidden[root]}")

    def test_every_deciding_module_is_in_the_domain(self) -> None:
        present = {path.stem for path in self.domain_files()}
        missing = sorted(self.DECIDING_MODULES - present)
        assert not missing, (
            f"{missing} left the domain. Every routing decision lives there, and a "
            "decision in a swappable component is a decision a broken adapter can "
            "change."
        )


class TestTheSiblingsAreOptional:
    """ADR-0005 and ADR-0009, at the AST level.

    `import-linter` asserts the same thing and is the check that runs in CI.
    This exists because the message matters: a contract failure names a module
    graph, and the person who just wrote `import mamori` in the domain needs to
    read why that is wrong, not where.
    """

    @pytest.mark.parametrize("path", ALL_FILES, ids=FILE_IDS)
    def test_only_an_adapter_may_name_mamori(self, path: Path) -> None:
        if "mamori" not in imported_roots(path):
            return
        assert layer_of(path) == "infrastructure", (
            f"{path.relative_to(PACKAGE_ROOT)} imports mamori. Only an adapter in "
            "infrastructure/ may: the core has to stand alone, so that a person who "
            "wants only a router gets one."
        )

    @pytest.mark.parametrize("path", ALL_FILES, ids=FILE_IDS)
    def test_nothing_at_all_imports_tsumugi(self, path: Path) -> None:
        assert "tsumugi" not in imported_roots(path), (
            f"{path.relative_to(PACKAGE_ROOT)} imports tsumugi. That seam is a "
            "published JSON contract; reading it is reading JSON. ADR-0009."
        )
