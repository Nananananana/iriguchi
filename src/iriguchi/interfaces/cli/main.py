"""The command line. The composition root, and the only place adapters are named.

`route` is the one the project is named after, and `iriguchi algorithms` is the
one that says what could sit behind each port and what each choice costs.

The command count used to be written here as a number. It went stale the first
time a command was added, which is what a count in prose does -- and this
repository spent a week building checks for exactly that shape.

**`--dry-run` is not a flag on a command that would otherwise send.** Through
v0.1 there is no outbound path anywhere in this package, so `route` never sends
whatever you pass it. The flag exists so the guarantee is written where people
read it, and so that v0.2 -- which does add an outbound path, in `ask` -- has to
keep `route` true rather than invent the promise later.

Exit codes distinguish three things a caller cares about: a decision was made, a
decision was made and it was a refusal, or no decision could be made. A script
that treats a refusal as a crash will retry it forever.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import NoReturn, TextIO

from ...application.asking import Answer
from ...application.routing import PromptRouter
from ...config import ENV_PREFIX, IriguchiConfig
from ...domain.destination import Destination, Route
from ...domain.sensitivity import Finding
from ...errors import (
    ConfigurationError,
    EscalationRefusedError,
    IriguchiError,
    safe_detail,
)
from ...evaluation.case import Case
from ...evaluation.dataset import load_corpus
from ...evaluation.scoring import run as run_evaluation
from ...infrastructure.registry import ESTIMATORS, JUDGES, SCANNERS
from ...infrastructure.scanners.mamori_scanner import (
    SiblingState,
    mamori_is_available,
    mamori_state,
)
from ..contract import CONTRACT, SCHEMAS, as_document, schema
from .console import print_content
from .render import render_decision

__all__ = ["main"]

#: A decision was made and something can happen.
EXIT_OK = 0
#: The tool failed: a bad setting, an unreadable corpus.
EXIT_ERROR = 1
#: A decision was made and it was `REFUSED`. Not a failure -- the router worked,
#: and the answer was no. A caller that cannot tell these apart will retry a
#: refusal until it gives up.
EXIT_REFUSED = 2

#: What `demo` runs. Chosen to show both axes and the trap between them.
DEMO_PROMPTS = (
    "この記事を三行で要約してください。",
    "この二つのアルゴリズムを比較して、計算量を証明してください。",
    "この二つを比較して証明してください。連絡先は tanaka@example.com です。",
)


class _Parser(argparse.ArgumentParser):
    """argparse, with iriguchi's exit codes rather than argparse's.

    **A mistyped flag was arriving as a routing refusal.** argparse exits `2`
    for a usage error; iriguchi publishes `2` as *refused*, which is a decision
    it stands behind. Sora maps `2` to `refused` and deliberately does not
    colour it as an error, so `iriguchi --nosuchflag route "..."` reached a
    person as *your prompt was refused* -- with no decision document anywhere,
    because none had been made. A false statement about a policy decision,
    produced by a typo.

    Measured before it was changed. The README's own sentence had said which
    code this should be since before the collision existed: `0` decided, `2`
    refused, `1` broken.

    The message comes out **before** the usage block and named as a
    `ConfigurationError`, which is not a new kind: *a setting was missing,
    malformed, or not recognised* is exactly what a bad flag is. That puts the
    name first on stderr, where R-E2 needs it, and puts the error above the
    usage text, where a person reads it.
    """

    def error(self, message: str) -> NoReturn:
        print(f"ConfigurationError: {message}", file=sys.stderr)
        self.print_usage(sys.stderr)
        raise SystemExit(EXIT_ERROR)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="iriguchi",
        description=(
            "Decide where a prompt is allowed to go -- locally, deterministically, "
            "and before anything leaves this machine."
        ),
    )
    parser.add_argument(
        "--local",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether a local model is available (default: from IRIGUCHI_LOCAL)",
    )
    parser.add_argument(
        "--external",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether an external service is reachable (default: from IRIGUCHI_EXTERNAL)",
    )

    parser.add_argument(
        "--scanner",
        # From the registry rather than typed here. A `choices=` list copied
        # into the parser is a second place to add an algorithm, and the one
        # that gets forgotten.
        choices=SCANNERS.names,
        default=None,
        help=(
            "which sensitivity scanner to use. Defaults to the built-in fallback even "
            "when mamori is installed: changing the scanner changes what leaves this "
            "machine, and that is not a thing to inherit from what happens to be on "
            "the system."
        ),
    )

    parser.add_argument(
        "--judge",
        choices=(*JUDGES.names, "consistency"),
        default=None,
        help=(
            "inspect the local answer and escalate it if it looks weak. Off by "
            "default: `consistency` re-asks the local model, which doubles local "
            "latency, and escalation only ever reaches a destination the routing "
            "decision had already permitted."
        ),
    )

    parser.add_argument(
        "--estimator",
        choices=ESTIMATORS.names,
        default=None,
        help=(
            "which complexity estimator to use. Defaults to "
            f"{ESTIMATORS.default!r}, or IRIGUCHI_ESTIMATOR."
        ),
    )

    commands = parser.add_subparsers(dest="command", required=True)

    route = commands.add_parser("route", help="where would this prompt go, and why")
    route.add_argument(
        "prompt",
        nargs="?",
        help=(
            "the prompt. Use - to read standard input as UTF-8, whatever the "
            "console's code page. Omitted only with --batch."
        ),
    )
    route.add_argument(
        "--findings",
        metavar="PATH",
        help=(
            "a JSON array of Presidio-shaped results (`entity_type`, `start`, `end`) "
            "from your own analyzer, used INSTEAD of running a scanner here. `-` "
            "reads them from standard input, in which case the prompt cannot also "
            "be `-`. Their `score` is discarded: the veto has no degrees."
        ),
    )
    route.add_argument(
        "--batch",
        action="store_true",
        help=(
            "read JSON Lines from standard input -- one object per line with "
            "`prompt` and optionally `id` and `findings` -- and write one decision "
            "per line, in order, as `iriguchi.route-batch/1-draft`. One process for "
            "many prompts: the interpreter costs about 85 ms and this pays it once. "
            "Implies --json. Every line is validated before any is routed, so a "
            "malformed line fails the whole batch with nothing written."
        ),
    )
    route.add_argument(
        "--explain",
        action="store_true",
        help="print every finding and signal, not just the reasons",
    )
    route.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "decide and send nothing. Accepted and ignored: nothing in v0.1 can send, "
            "and the flag is here so the promise survives v0.2."
        ),
    )
    route.add_argument(
        "--json",
        action="store_true",
        help=(
            "write the decision as `iriguchi.routing-decision/1` instead of prose. "
            "Carries rule ids, spans and bands and no part of your prompt; "
            "`iriguchi schema` prints the shape."
        ),
    )

    ask = commands.add_parser("ask", help="route this prompt, then answer it")
    ask.add_argument("prompt", help="the prompt. Use - to read standard input.")
    ask.add_argument(
        "--explain",
        action="store_true",
        help="print every finding and signal, not just the reasons",
    )
    ask.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "decide, show what would be sent, and send nothing. Not the same flag "
            "as `route --dry-run`, which is accepted and ignored because routing "
            "cannot send at all; here it is the difference between a question "
            "answered and a question asked."
        ),
    )

    commands.add_parser("config", help="what this configuration does with your prompts")
    published = commands.add_parser("schema", help="the JSON contract `route --json` writes")
    published.add_argument(
        "contract",
        nargs="?",
        default=CONTRACT,
        choices=sorted(SCHEMAS),
        help=(
            "which published document to print the schema for. Defaults to the frozen "
            "routing decision -- the one a caller with no opinion means."
        ),
    )
    commands.add_parser(
        "rules", help="every rule identifier a decision can carry, and what each means"
    )
    commands.add_parser(
        "errors", help="every named failure iriguchi can print, and the ones that are not failures"
    )
    commands.add_parser("algorithms", help="what can sit behind each port, and what each one costs")
    commands.add_parser("doctor", help="what is available, and what a missing piece costs")
    commands.add_parser("demo", help="a few prompts through the router")

    evaluate = commands.add_parser("eval", help="run the labelled corpus and report")
    evaluate.add_argument(
        "--source", help="only cases from this source, e.g. generated, borrowed:mamori"
    )
    evaluate.add_argument(
        "--corpus",
        metavar="DIR",
        help=(
            "score cases from this directory instead of the built-in corpus. The "
            "prompts stay on your machine -- the report carries case ids, rates and "
            "counts, and no prompt text. See docs/feasibility.md F1 for why "
            "somebody else's prompts are the measurement iriguchi cannot make."
        ),
    )
    return parser


def _config(args: argparse.Namespace) -> IriguchiConfig:
    """The flags win over the environment; the environment wins over nothing.

    `replace` rather than a fresh `IriguchiConfig(...)`. The constructor call
    listed the three fields that existed when it was written, so every field
    added afterwards would have been read from the environment and then
    silently dropped here -- and `ask`'s endpoint settings were about to be the
    first. A copy-with-overrides carries what it was not told about.
    """
    return replace(
        IriguchiConfig.from_env(),
        **{
            name: value
            for name, value in (
                ("local", args.local),
                ("external", args.external),
            )
            if value is not None
        },
        # `--scanner` used to arrive here as `use_mamori=args.scanner ==
        # "mamori"` and nothing else, so every other name -- including every
        # name the registry offers -- was accepted by the parser and then
        # replaced by the default with nothing said. A user who selected a
        # scanner got a different one, which the registry's own refusal message
        # calls the worst available outcome.
        **({"scanner": args.scanner} if getattr(args, "scanner", None) else {}),
        **({"estimator": args.estimator} if getattr(args, "estimator", None) else {}),
        **({"judge": args.judge} if getattr(args, "judge", None) else {}),
    )


def _read(prompt: str) -> str:
    """The prompt, from the argument or -- for `-` -- from standard input.

    **Standard input is decoded as UTF-8 regardless of the locale**, and this
    was found by piping Japanese into `route --json -` on a Windows machine
    without `PYTHONUTF8`. `sys.stdin.read()` decoded it as cp932, the honorific
    finding **disappeared**, and the email span shifted by four -- a veto miss
    caused by an encoding default. Sora's requirement said UTF-8 in one word;
    this is why it had to.

    Read as bytes and decoded explicitly, so the caller's console code page is
    not a routing input. A prompt that is not valid UTF-8 is refused rather than
    decoded leniently, because a replacement character at offset 12 is a span
    into text nobody sent.
    """
    if prompt != "-":
        return prompt
    # A real console stream carries `.buffer`; a `StringIO` handed in by a test
    # does not, and is already text. The fallback exists for the double, never
    # for a person -- every stdin a process is given has bytes underneath.
    binary = getattr(sys.stdin, "buffer", None)
    if binary is None:
        return str(sys.stdin.read())
    raw: bytes = binary.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as failure:
        raise ConfigurationError(
            f"standard input is not valid UTF-8 (byte {failure.start}: {failure.reason}). "
            f"`route -` reads UTF-8 whatever the console's code page, so a caller "
            f"has to send it that way -- decoding leniently would produce spans "
            f"into text nobody sent."
        ) from failure


def cmd_schema(args: argparse.Namespace, out: TextIO) -> int:
    """One published contract, from the installed package.

    Printed rather than linked, because a consumer generating code from it
    should be reading the one in the wheel they have and not the one on a branch
    somebody is editing.

    All three are reachable here. Two of them were reachable only as an example
    in a reply, which is a shape a consumer has to infer from output -- and Sora
    vendored one on exactly that basis.
    """
    print(json.dumps(schema(args.contract), ensure_ascii=False, indent=2), file=out)
    return EXIT_OK


def cmd_rules(out: TextIO) -> int:
    """Every rule identifier a decision can carry, as `iriguchi.rules/1-draft`.

    A consumer keys its translations off `rule`, so it needs to know when a new
    one arrives -- otherwise a reader of Japanese meets `policy.something-new`
    in raw ASCII. Sora tests its locale files against this.

    The document has two halves and the second is the honest one: `presidio.*`
    and `mamori.*` are `f"{source}.{entity_type}"` from a foreign detector, so
    which identifiers exist depends on that detector's configuration and
    iriguchi cannot enumerate them. Those are declared as prefixes with a
    sentence each, which is translatable even when the entity type is new.
    """
    from ... import __version__
    from ..rules import as_document as rules_document

    print(json.dumps(rules_document(__version__), ensure_ascii=False, indent=2), file=out)
    return EXIT_OK


def cmd_route(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    if args.batch:
        return _route_batch(args, config, out)
    if args.prompt is None:
        raise ConfigurationError("route needs a prompt, or --batch. `-` reads standard input.")
    if args.findings == "-" and args.prompt == "-":
        raise ConfigurationError(
            "--findings - and a prompt of - would both read standard input, and one "
            "stream cannot carry two documents. Put one of them in a file."
        )
    router = _router_with(config, _findings_from(args.findings))
    prompt = _read(args.prompt)
    decision = router.route(prompt, config.available)

    if args.json:
        # `ensure_ascii=False` so a Japanese rule id stays readable in a
        # terminal and in `jq`; the document holds no prompt text either way.
        #
        # **Insertion order, not sorted.** `as_document` builds the keys in a
        # fixed order, so diffs are already stable -- and sorting put `by`
        # ahead of `contract`, which contradicts the one thing a consumer is
        # supposed to read first. JSON objects are unordered by spec and a
        # human scanning a terminal is not.
        print(
            json.dumps(as_document(decision, config.thresholds()), ensure_ascii=False, indent=2),
            file=out,
        )
        return EXIT_REFUSED if decision.route is Route.REFUSED else EXIT_OK

    print(
        render_decision(decision, sent="nothing", verbose=args.explain),
        file=out,
    )
    if args.explain and decision.route is Route.EXTERNAL:
        _what_would_leave(config, prompt, out)
    if decision.route is Route.REFUSED:
        _what_would_change_this(config, out)
    return EXIT_REFUSED if decision.route is Route.REFUSED else EXIT_OK


def _findings_from(source: str | None) -> tuple[Finding, ...] | None:
    """Presidio-shaped results from a file or standard input, or `None`.

    `None` and an empty tuple are different answers and both are kept: `None`
    means *run a scanner*, `()` means *my analyzer found nothing, do not scan*.
    Collapsing them would turn a clean bill of health into a request for a
    second opinion, silently.
    """
    if source is None:
        return None
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        # `OSError` is not an `IriguchiError`, so without this a missing file
        # reached `main` untouched and printed a Python traceback -- to a caller
        # that spawns this as a subprocess and reads stderr. A tool asked for a
        # path it cannot read should say so in its own voice and exit 1.
        try:
            raw = Path(source).read_bytes()
        except OSError as failure:
            raise ConfigurationError(
                f"--findings could not read {source!r}: {failure.strerror or failure}. "
                f"It wants a file holding a JSON array, or `-` for standard input."
            ) from failure
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        raise ConfigurationError(f"--findings is not a UTF-8 JSON document: {failure}") from failure
    if not isinstance(loaded, list):
        raise ConfigurationError(
            f"--findings must be a JSON array of results, the shape "
            f"`[r.to_dict() for r in analyzer.analyze(...)]` produces; got "
            f"{type(loaded).__name__}."
        )
    from ...interop import findings_from_presidio

    return findings_from_presidio(loaded)


def _router_with(config: IriguchiConfig, findings: tuple[Finding, ...] | None) -> PromptRouter:
    """The configured router, with the scanner replaced when findings came in.

    The same rule the library's `route()` applies: findings from elsewhere and a
    scanner named here are two intentions, and guessing which one somebody meant
    would decide what leaves the machine on a coin toss.
    """
    router: PromptRouter = config.router()
    if findings is None:
        return router
    if config.scanner:
        raise ConfigurationError(
            f"both --findings and a scanner ({config.scanner!r}) were given. Findings "
            f"from elsewhere replace the scan; naming a scanner says to run one. Pick "
            f"the one you meant."
        )
    from ...infrastructure.scanners.supplied import SuppliedScanner

    return replace(router, scanner=SuppliedScanner(findings))


#: The envelope one batch line travels in. A draft, and not the frozen
#: `routing-decision/1`, which is inside it untouched: the frozen document cannot
#: grow an `id`, and a consumer routing five prompts in one call needs to know
#: which answer is whose.
BATCH_CONTRACT = "iriguchi.route-batch/1-draft"


def _route_batch(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    """Many prompts, one process, one decision per line and in order.

    **Every line is parsed and checked before any is routed.** A batch that
    wrote three decisions and then died on the fourth line would leave a
    consumer holding output it cannot tell apart from a complete run -- the
    same reason `findings_from_presidio` refuses a whole batch on one bad item.
    Nothing is written until everything is known to be well-formed.

    Exit code follows the strictest line: `2` if any prompt was refused,
    otherwise `0`. A malformed input is `1` with nothing written, because that
    is a broken call rather than a decision.
    """
    if args.prompt is not None and args.prompt != "-":
        raise ConfigurationError(
            "--batch reads standard input; a prompt argument has nowhere to go."
        )
    if args.findings is not None:
        raise ConfigurationError(
            "--findings is per prompt; in --batch mode put a `findings` array on each line."
        )

    lines = sys.stdin.buffer.read().decode("utf-8").splitlines()
    jobs: list[tuple[object, str, tuple[Finding, ...] | None]] = []
    from ...interop import findings_from_presidio

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as failure:
            raise ConfigurationError(f"batch line {number} is not JSON: {failure}") from failure
        if not isinstance(item, dict) or not isinstance(item.get("prompt"), str):
            raise ConfigurationError(
                f"batch line {number} needs an object with a string `prompt`; "
                f"optional keys are `id` and `findings`."
            )
        unknown = set(item) - {"id", "prompt", "findings"}
        if unknown:
            raise ConfigurationError(
                f"batch line {number} has keys nobody reads: {sorted(unknown)}. Refused "
                f"rather than ignored -- a misspelled `findings` would silently run a "
                f"scan the caller thought they had replaced."
            )
        found = None
        if "findings" in item:
            if not isinstance(item["findings"], list):
                raise ConfigurationError(f"batch line {number}: `findings` must be an array")
            found = findings_from_presidio(item["findings"])
        jobs.append((item.get("id"), item["prompt"], found))

    if not jobs:
        raise ConfigurationError("--batch read no prompts. One JSON object per line, please.")

    thresholds = config.thresholds()
    worst = EXIT_OK
    for identifier, prompt, found in jobs:
        decision = _router_with(config, found).route(prompt, config.available)
        if decision.route is Route.REFUSED:
            worst = EXIT_REFUSED
        envelope = {
            "contract": BATCH_CONTRACT,
            "id": identifier,
            "decision": as_document(decision, thresholds),
        }
        print(json.dumps(envelope, ensure_ascii=False), file=out)
    return worst


def _what_would_change_this(config: IriguchiConfig, out: TextIO) -> None:
    """After a refusal: the settings that would have produced an answer.

    A refusal that names the obstacle and not the remedy is a dead end wearing
    an explanation. `doctor` has said all of this since v0.1 -- to somebody who
    already knew to run it, which is not the person who just got told no.

    Only settings, never a suggestion to relax the veto. There is no advice here
    of the form *scan less*: the destinations are what is missing, and a
    sensitive prompt with a local model reaches one.
    """
    missing = []
    if Destination.LOCAL not in config.available:
        missing.append(
            f"  {ENV_PREFIX}LOCAL=1                 a local model exists. A prompt that "
            f"must stay local is refused without one -- that is ADR-0002 working, "
            f"and it is also most of what you would want to ask."
        )
    if Destination.EXTERNAL not in config.available:
        missing.append(
            f"  {ENV_PREFIX}EXTERNAL=1              an external service is reachable. "
            f"Only prompts with no findings can use it, whatever their difficulty."
        )
    if not missing:
        return
    print("\n  what would change this", file=out)
    for line in missing:
        print(line, file=out)
    print(
        "\n  Nothing above weakens the scan. `iriguchi doctor` says what is "
        "configured and what each absence costs.",
        file=out,
    )


def cmd_ask(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    """The only command that sends, and the only one that can be wrong twice.

    A refusal is printed and nothing runs. Everything else prints the route
    first, then the answer -- in that order on purpose, so that a person reading
    a terminal sees where their words went before they see what came back.

    **`--dry-run` returns before anything that can send is constructed**, and
    that is a structural promise rather than an ordering one. The first version
    built the `Asker` first, which builds the channel, which needs mamori -- so
    `ask --dry-run` failed outright on a machine without it, having refused to
    do the one thing the flag exists for. A flag that means "decide and send
    nothing" cannot require the sending half to be available.
    """
    from ...application.asking import Asker

    prompt = _read(args.prompt)
    if args.dry_run:
        return _decide_only(args, config, prompt, out)

    asker = Asker(
        router=config.router(),
        local=config.local_answerer() if config.local else None,
        external=config.external_answerer() if config.external else None,
        channel=config.channel() if config.external else None,
        judge=config.answer_judge(),
    )
    answer = asker.ask(prompt, config.available)
    print(
        render_decision(
            answer.decision,
            sent=("nothing" if not answer.answered else f"the prompt, to {answer.model}"),
            verbose=args.explain,
        ),
        file=out,
    )
    if not answer.answered:
        return EXIT_REFUSED

    _report_cascade(answer, out)

    # ADR-0013: iriguchi only escalates when its own scanner said CLEAR, so
    # anything mamori protected on the way out is something the scanner missed.
    # Printed before the answer, because it is about the decision rather than
    # about the reply, and a person scrolling to the answer would never see it
    # underneath.
    for missed in answer.missed:
        print(f"\n  missed by the scanner  {missed.detail}", file=out)

    print(f"\n{answer.model} answered:\n", file=out)
    # `answered` is checked above, so `text` is a string here. Asserted rather
    # than cast: `None` means a refusal and printing the word "None" under
    # "answered:" would be a model appearing to say something.
    assert answer.text is not None
    print_content(answer.text, out)
    if answer.superseded is not None:
        print("\nthe local answer this replaced:\n", file=out)
        print_content(answer.superseded, out, indent="  ")
    return EXIT_OK


def _report_cascade(answer: Answer, out: TextIO) -> None:
    """What the judge thought, when one ran.

    Printed **above** the answer, like the route is, and for the same reason:
    somebody reading a terminal should see how they got this answer before they
    see the answer. A cascade that silently replaced a local answer with an
    external one would be the single most surprising thing this tool could do.

    Silent when no judge was configured. An absent judge is not an opinion, and
    a line saying "not judged" on every ordinary run is a line people stop
    reading.
    """
    if answer.escalation is None:
        return
    print(f"\n  cascade      {answer.escalation.reason.detail}", file=out)
    if answer.quality is not None and answer.quality.signals:
        rules = ", ".join(signal.rule for signal in answer.quality.signals)
        print(f"      the local answer showed {rules}", file=out)
    if answer.cascaded:
        print(
            "      the local answer below was replaced; it is kept because "
            "you are entitled to see it",
            file=out,
        )


def _decide_only(args: argparse.Namespace, config: IriguchiConfig, prompt: str, out: TextIO) -> int:
    """Decide, show what would leave, and construct nothing that could send.

    `_what_would_leave` protects and closes; there is no send on that path,
    which is what lets an inspection command walk it, and it says so in prose
    when the protection is unavailable rather than failing the command.
    """
    decision = config.router().route(prompt, config.available)
    print(render_decision(decision, sent="nothing", verbose=args.explain), file=out)
    if decision.route is Route.EXTERNAL:
        _what_would_leave(config, prompt, out)
    print("\nNothing was asked. Drop --dry-run to send it.", file=out)
    return EXIT_REFUSED if decision.route is Route.REFUSED else EXIT_OK


def _what_would_leave(config: IriguchiConfig, prompt: str, out: TextIO) -> None:
    """The protected text, for an outbound route. Sends nothing.

    The first thing `--dry-run` has ever had that is worth looking at: not
    *where* a prompt would go but *what* would arrive. `prepare` protects and
    returns; there is no send on that path, which is what lets an inspection
    command walk it.

    The escalation is closed immediately. It exists to be looked at, and the
    mapping it holds is the highest-value object in the round trip -- holding
    one open for the length of somebody's attention span is not a reason to
    hold one.
    """
    try:
        channel = config.channel()
    except EscalationRefusedError as refused:
        print(f"\n  would leave    (cannot say: {refused})", file=out)
        return

    try:
        escalation = channel.prepare(prompt)
    except EscalationRefusedError as refused:
        # Not a crash and not a downgrade. The route stands; the protection
        # that route depends on refused, and the person needs to know which.
        print(
            f"\n  would leave    nothing -- the escalation was refused:\n      {refused}",
            file=out,
        )
        return

    try:
        # Through `print_content`, because this is the one line here carrying
        # characters the person typed. A console that cannot draw them would
        # otherwise kill the command -- the command whose whole purpose is
        # letting somebody look before anything leaves.
        print("\n  would leave", file=out)
        print_content(escalation.protected_text, out, indent="    ")
        if escalation.findings:
            print("\n  and the scanner had missed", file=out)
            for finding in escalation.findings:
                print(f"    {finding.rule:<40}{finding.detail}", file=out)
    finally:
        escalation.close()


def cmd_errors(out: TextIO) -> int:
    """Every named failure, as `iriguchi.errors/1-draft`.

    Sora keeps a ledger of what is not working and folds repeated failures into
    one row keyed on the kind, holding **no values** -- so they need to know
    which kinds exist, what each one means, and whether trying again is a thing
    a consumer may do. They copied the shape from `rules --json` and said so.

    The document has a third half the rules catalogue does not: `not_a_failure`,
    for the exceptions iriguchi raises and never prints. A consumer that saw
    only `errors` would conclude a broken scanner produces nothing, when what it
    produces is a decision -- the most restrictive one available, with a reason
    naming what broke.
    """
    from ... import __version__
    from ..error_catalogue import as_document as errors_document

    print(json.dumps(errors_document(__version__), ensure_ascii=False, indent=2), file=out)
    return EXIT_OK


def cmd_algorithms(config: IriguchiConfig, out: TextIO) -> int:
    """The menu, with prices.

    Every registry entry carries the trade it makes, because a list of names is
    a menu with no prices and this project's whole argument is that the price is
    the interesting part. Availability is reported per entry: "there is no such
    algorithm" and "you do not have that one" send a reader to fix different
    things.
    """
    for title, registry, chosen in (
        ("scanners", SCANNERS, config.scanner_name()),
        ("estimators", ESTIMATORS, config.estimator),
    ):
        print(f"\n  {title}", file=out)
        for choice in registry:
            usable, detail = choice.available()
            mark = "*" if choice.name == (chosen or registry.default) else " "
            state = "" if usable else f"  -- unavailable: {detail}"
            print(f"    {mark} {choice.name:<10} {choice.summary}{state}", file=out)
            print(f"      {choice.trade}", file=out)
    cut = config.thresholds()
    print(
        f"\n  bands            moderate at {cut.moderate_at}, high at {cut.high_at}, "
        f"or {cut.short_circuit_at} escalating signals",
        file=out,
    )
    print(
        "  `* ` is what this configuration would use. "
        "`python tools/calibrate.py --escalate 0.3` derives the band numbers "
        "from a target rate instead of inventing one.",
        file=out,
    )
    return EXIT_OK


def cmd_config(config: IriguchiConfig, out: TextIO) -> int:
    print(config.describe(), file=out)
    return EXIT_OK


def cmd_doctor(config: IriguchiConfig, out: TextIO) -> int:
    """What is missing, and what its absence costs.

    Worth more than it looks. ADR-0002 means a missing local model turns a whole
    class of prompt into refusals, so the tool says that plainly rather than
    letting somebody discover it mid-sentence.
    """
    lines = [config.describe(), ""]
    if Destination.LOCAL not in config.available:
        lines.append(
            "warning: with no local model, every prompt containing anything sensitive "
            "is refused. That is fail-closed working as intended (ADR-0002), and it is "
            "also most of what you would want to ask."
        )
    if config.scanner_name() == "mamori":
        lines.append(
            "scanner: mamori. It misses far less than the fallback -- 1.0% against "
            "67.3% on its own corpus -- and over-detects more, which is the trade. "
            "See docs/measurements.md, including what that measurement does not say."
        )
    elif mamori_is_available():
        lines.append(
            "note: mamori is installed and not being used. The built-in fallback "
            "misses names without an honorific, English names, company names and "
            "addresses entirely. Pass --scanner mamori."
        )
    elif mamori_state()[0] is SiblingState.BROKEN:
        lines.append(
            f"warning: mamori is installed and will not import ({mamori_state()[1]}). "
            "That is not the same as it being absent, and telling you to install it "
            "would send you to fix the wrong thing. iriguchi is using the fallback."
        )
    else:
        # **The remedy has to be one the reader can actually run.** This note
        # said "install mamori" for as long as mamori was the only better
        # scanner, and mamori is not on PyPI -- so it named the miss rate and
        # then pointed at a package nobody outside this machine can get. Now
        # that a followable answer exists it goes first, and the unreachable one
        # is named for what it is.
        usable, _ = SCANNERS.describe("presidio").available()
        remedy = (
            "`iriguchi --scanner fallback+presidio` runs both and misses 27.1%"
            if usable
            else 'install `pip install "iriguchi[presidio]"` plus a spaCy model '
            "and run `--scanner fallback+presidio`, which misses 27.1%"
        )
        lines.append(
            "note: the built-in scanner over-detects on purpose and misses 61.7% "
            "of must-stay-local cases -- names without an honorific, English "
            f"names, company names and addresses entirely. {remedy}. mamori is "
            "better still and is not on PyPI. See docs/measurements.md for the "
            "trade each one makes."
        )
    print("\n".join(lines), file=out)
    return EXIT_OK


def cmd_demo(config: IriguchiConfig, out: TextIO) -> int:
    router = config.router()
    for prompt in DEMO_PROMPTS:
        print(f"\n$ iriguchi route {prompt!r}\n", file=out)
        decision = router.route(prompt, config.available)
        print(render_decision(decision, sent="nothing"), file=out)
    return EXIT_OK


def cmd_eval(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    """No model. Ever. ADR-0007.

    `--corpus` is a seam somebody else's file crosses, and this session has
    already been taught twice what those cost: a bare `OSError` from an
    unreadable `--findings` file, and a `ValueError` from a span the domain
    refuses. Both escaped the handler as tracebacks. So everything the loader
    can raise is turned into a `ConfigurationError` here -- a kind that is in
    `iriguchi errors`, exits 1, and prints its name first.
    """
    cases = _corpus(args.corpus)
    if args.source:
        cases = tuple(case for case in cases if case.source == args.source)
        if not cases:
            print(f"no cases from source {args.source!r}", file=out)
            return EXIT_ERROR
    report = run_evaluation(config.router(), cases)
    print(report.render(), file=out)
    return EXIT_OK


def _corpus(directory: str | None) -> tuple[Case, ...]:
    """The built-in corpus, or one somebody else holds.

    The loader has always taken a directory; nothing exposed it. That is the
    smaller half of what `--corpus` is for -- the larger half is that
    `docs/feasibility.md` F1 asks for a measurement iriguchi structurally cannot
    make, because every prompt that asks the complexity axis a question was
    written by the people who wrote the axis. Somebody else's prompts are the
    only answer, and their prompts cannot come here.

    So the measurement goes to them. The report carries rates, counts and the
    case ids they chose, and no prompt text -- asserted, not asserted-to.
    """
    if directory is None:
        return load_corpus()
    root = Path(directory)
    if not root.is_dir():
        raise ConfigurationError(
            f"--corpus {directory!r} is not a directory. It should hold one or more "
            f"corpus JSON files in the shape of `src/iriguchi/evaluation/data/*.json`; "
            f"`iriguchi eval` with no --corpus scores the built-in one."
        )
    try:
        cases = load_corpus(root)
    except IriguchiError:
        raise
    except Exception as failure:
        # The loader predates this flag and raises `KeyError`, `ValueError` and
        # `OSError` for a malformed file -- none of them an `IriguchiError`, so
        # each would have reached a person as a traceback and Sora as a failure
        # with no name. `safe_detail` keeps the class and drops the message,
        # because a JSON parser quotes what it choked on (ADR-0021).
        raise ConfigurationError(
            f"--corpus {directory!r} holds a file iriguchi could not read "
            f"({safe_detail(failure)}). Every file must match the shape of "
            f"`src/iriguchi/evaluation/data/*.json`: a `samples` list, and each "
            f"sample with an `id`, a `prompt`, a sensitivity class and a band."
        ) from failure
    if not cases:
        raise ConfigurationError(
            f"--corpus {directory!r} is a directory with no corpus files in it. "
            f"An empty corpus scores 100% on everything, which is the shape of a "
            f"check that cannot fail rather than a passing one."
        )
    return cases


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Entry point. Returns an exit code rather than raising."""
    stream = sys.stdout if out is None else out
    args = build_parser().parse_args(argv)

    try:
        config = _config(args)
        if args.command == "route":
            return cmd_route(args, config, stream)
        if args.command == "ask":
            return cmd_ask(args, config, stream)
        if args.command == "config":
            return cmd_config(config, stream)
        if args.command == "schema":
            return cmd_schema(args, stream)
        if args.command == "rules":
            return cmd_rules(stream)
        if args.command == "errors":
            return cmd_errors(stream)
        if args.command == "algorithms":
            return cmd_algorithms(config, stream)
        if args.command == "doctor":
            return cmd_doctor(config, stream)
        if args.command == "demo":
            return cmd_demo(config, stream)
        if args.command == "eval":
            return cmd_eval(args, config, stream)
    except IriguchiError as failure:
        # **The kind first, then the sentence.** Sora folds repeated failures
        # into one incident row keyed on the name before the colon, and keeps no
        # values -- so this line was `iriguchi: <message>` and four unrelated
        # failures folded into a single row called `iriguchi`, which carries the
        # same information as a counter. R-E2 was filed as a request rather than
        # a requirement; it was the more urgent half.
        #
        # The sentence after the colon is unconstrained and stays as it was. It
        # is read by the person at the terminal, who is the one entitled to it.
        print(f"{type(failure).__name__}: {failure}", file=sys.stderr)
        return EXIT_ERROR

    # Unreachable while `add_subparsers(required=True)` holds. Kept as a
    # raise rather than a silent `return EXIT_OK`, because a command that
    # was added to the parser and not to this chain should stop loudly
    # rather than exit zero having done nothing.
    raise AssertionError(  # pragma: no cover
        f"unreachable: argparse accepted {args.command!r}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
