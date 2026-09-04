"""Does the suite actually catch a wrong decision, or only run over one?

    python tools/mutate.py
    python tools/mutate.py --target "src/iriguchi/infrastructure/**/*.py"

Every check in this repository has been asked *would this go red* by hand, one
at a time, by breaking the thing it guards. This does it exhaustively and
mechanically: change one operator, run the tests, and see whether anybody
noticed.

**A surviving mutant is a sentence the suite cannot distinguish from the truth.**
Not necessarily a bug — some mutations are genuinely equivalent — but every one
is a place where the code could be wrong and the tests would agree.

## Why this is written here rather than installed

`mutmut` refuses to run on Windows, which is the machine this project is
developed on. `cosmic-ray` runs, and adds **726 lines to `uv.lock`** — aiohttp,
yarl, textual — for a repository whose stated identity is *a tool that sees
every prompt you type is a tool whose dependency list is a threat model*. A
development dependency is still code that runs on a developer's machine with
the source in front of it.

So: the standard library, about two hundred lines, and the same place
`measure_memory.py` and `measure_router.py` live. A measurement instrument is
not a feature.

## Two stages, because a narrow scope is how a check reports about nothing

    stage 1   a fast subset -- most mutants die here
    stage 2   **every survivor re-run against the whole suite**

A mutant that survives stage 1 and dies in stage 2 was never a survivor: the
test that kills it simply lives somewhere the subset did not look. Reporting
stage 1 alone would name real tests as missing.

## Three outcomes, not two

    KILLED     a test failed. The suite can tell
    SURVIVED   every test passed. The suite cannot
    INVALID    the mutant does not import or parse

`INVALID` is separate on purpose. A mutant that breaks at import time proves
nothing about the tests, and counting it as killed would flatter the score with
the compiler's work.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Comparison operators, swapped for the neighbour a fencepost error would
#: produce. `<` for `<=` is the mutation that finds a threshold nobody tested at
#: its boundary, which is most of what a band function is.
COMPARISONS = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

#: `and` for `or`. In a fail-closed router this is the mutation that matters
#: most: it turns "both of these must hold before anything leaves" into "either
#: will do".
BOOLEANS = {ast.And: ast.Or, ast.Or: ast.And}


class Outcome(Enum):
    KILLED = "killed"
    SURVIVED = "survived"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Mutant:
    path: Path
    line: int
    description: str
    source: str


class _Mutator(ast.NodeTransformer):
    """Applies exactly one change, chosen by index.

    One at a time rather than all at once, because a module with two mutations
    tells you the suite noticed *something* and not which. The index is walked
    rather than randomised so a run is reproducible from its report.
    """

    def __init__(self, target: int) -> None:
        self.target = target
        self.found = 0
        self.description = ""
        self.line = 0
        self._keyword: str | None = None

    def _take(self, description: str, node: ast.AST) -> bool:
        """Records the line as well as the change.

        The first version returned a line of 0 for everything, which made the
        report a list of twenty-two changes with nowhere to look. A survivor
        you cannot find is a survivor you will not fix.
        """
        hit = self.found == self.target
        if hit:
            self.description = description
            self.line = getattr(node, "lineno", 0)
        self.found += 1
        return hit

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        for index, operator in enumerate(node.ops):
            replacement = COMPARISONS.get(type(operator))
            if replacement is None:
                continue
            if self._take(f"{type(operator).__name__} -> {replacement.__name__}", node):
                node.ops[index] = replacement()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        replacement = BOOLEANS.get(type(node.op))
        if replacement is not None and self._take(
            f"{type(node.op).__name__} -> {replacement.__name__}", node
        ):
            node.op = replacement()
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._take("drop a `not`", node):
            return node.operand
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        """Name the argument a mutated constant belongs to.

        Seven of this domain's dataclasses carry `frozen=True, slots=True`, and
        the first report called both mutations `True -> False` on the same
        line. **One of those is equivalent and the other is a real gap** --
        `slots` changes memory, `frozen` changes whether a decision can be
        edited after it was made -- and a report that cannot tell them apart
        makes the reader open the file to find out which. Fourteen times.
        """
        self._keyword = node.arg
        try:
            self.generic_visit(node)
        finally:
            self._keyword = None
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # Booleans and numbers only. Mutating a string turns a message into a
        # different message, which no test should be asserting on anyway --
        # and if one is, that is a finding about the test rather than the code.
        if isinstance(node.value, bool):
            named = f"{self._keyword}=" if self._keyword else ""
            if self._take(f"{named}{node.value} -> {not node.value}", node):
                return ast.copy_location(ast.Constant(value=not node.value), node)
        elif isinstance(node.value, int | float) and self._take(
            f"{self._keyword + '=' if self._keyword else ''}{node.value!r} -> {node.value + 1!r}",
            node,
        ):
            return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def _count(tree: ast.Module) -> int:
    counter = _Mutator(target=-1)
    counter.visit(tree)
    return counter.found


def mutants(path: Path) -> list[Mutant]:
    original = path.read_text(encoding="utf-8")
    total = _count(ast.parse(original))
    found: list[Mutant] = []
    for index in range(total):
        tree = ast.parse(original)
        mutator = _Mutator(target=index)
        mutated = ast.fix_missing_locations(mutator.visit(tree))
        # Not swallowed. A tree this mutator built that cannot be unparsed is a
        # bug in the mutator, and dropping it would shrink the denominator --
        # the population defect this whole repository keeps finding. Raised
        # with the address so it can be reproduced.
        try:
            source = ast.unparse(mutated)
        except Exception as failure:  # pragma: no cover - a mutator bug
            raise AssertionError(
                f"mutant {index} of {path} produced a tree that will not unparse: "
                f"{type(failure).__name__}: {failure}"
            ) from failure
        found.append(Mutant(path, mutator.line, mutator.description, source))
    return found


def run(command: list[str], seconds: float) -> bool:
    """True when the tests passed, which for a mutant means it survived."""
    try:
        finished = subprocess.run(  # noqa: S603
            command, cwd=ROOT, capture_output=True, timeout=seconds, check=False
        )
    except subprocess.TimeoutExpired:
        # A mutant that makes the suite hang is caught, not missed: an infinite
        # loop is a failure the suite noticed by never finishing.
        return False
    return finished.returncode == 0


def evaluate(mutant: Mutant, fast: list[str], full: list[str], seconds: float) -> Outcome:
    """Write a mutant, run the tests, put the file back exactly as it was.

    **Byte-for-byte**, including the line endings. The first version used
    `write_text` with no `newline`, which translates on Windows -- so a clean
    run left six domain files showing as modified with an empty diff, and a
    `mixed-line-ending` hook to argue with afterwards. The corpus generators in
    this repository learned the same thing.
    """
    original = mutant.path.read_bytes()
    try:
        mutant.path.write_text(mutant.source, encoding="utf-8", newline="\n")
        try:
            compile(mutant.source, str(mutant.path), "exec")
        except SyntaxError:
            return Outcome.INVALID
        if not run(fast, seconds):
            return Outcome.KILLED
        # Stage two. A survivor of the subset may simply be killed by a test the
        # subset did not run, and reporting it as a gap would name a test that
        # exists as missing.
        return Outcome.SURVIVED if run(full, seconds) else Outcome.KILLED
    finally:
        mutant.path.write_bytes(original)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default="src/iriguchi/domain/*.py")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--fast",
        default="tests/test_domain_values.py tests/test_routing_policy.py "
        "tests/test_routing_properties.py tests/test_routing_use_case.py",
        help="stage one. Every survivor of it is re-run against the whole suite.",
    )
    args = parser.parse_args(argv)

    paths = sorted(ROOT.glob(args.target))
    if not paths:
        print(f"no files matched {args.target!r}", file=sys.stderr)
        return 1

    fast = [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", *args.fast.split()]
    full = [sys.executable, "-m", "pytest", "-x", "-q", "--no-header"]

    print(f"{len(paths)} file(s) under {args.target}")
    survivors: list[Mutant] = []
    counts = dict.fromkeys(Outcome, 0)
    started = time.monotonic()

    for path in paths:
        found = mutants(path)
        print(f"\n{path.relative_to(ROOT)}  ({len(found)} mutants)", flush=True)
        for mutant in found:
            outcome = evaluate(mutant, fast, full, args.timeout)
            counts[outcome] += 1
            if outcome is Outcome.SURVIVED:
                survivors.append(mutant)
                print(f"  SURVIVED  line {mutant.line:4}  {mutant.description}", flush=True)
        print(f"  {counts[Outcome.KILLED]} killed so far", flush=True)

    total = sum(counts.values())
    scored = counts[Outcome.KILLED] + counts[Outcome.SURVIVED]
    print(f"\n{total} mutants in {time.monotonic() - started:.0f}s")
    for outcome in Outcome:
        print(f"  {outcome.value:9} {counts[outcome]}")
    if scored:
        # Over the ones that ran, and the denominator is stated: an `INVALID`
        # was never a question the suite was asked.
        print(f"  caught     {100 * counts[Outcome.KILLED] / scored:.1f}% of {scored} scored")
    if survivors:
        print("\nEvery survivor is a change the suite cannot tell from the truth:")
        for mutant in survivors:
            where = f"{mutant.path.relative_to(ROOT)}:{mutant.line}"
            print(f"  {where:44} {mutant.description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
