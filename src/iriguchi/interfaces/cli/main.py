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
from typing import TextIO

from ...application.asking import Answer
from ...application.routing import PromptRouter
from ...config import ENV_PREFIX, IriguchiConfig
from ...domain.destination import Destination, Route
from ...errors import EscalationRefusedError, IriguchiError
from ...evaluation.dataset import load_corpus
from ...evaluation.scoring import run as run_evaluation
from ...infrastructure.registry import ESTIMATORS, JUDGES, SCANNERS
from ...infrastructure.scanners.mamori_scanner import (
    SiblingState,
    mamori_is_available,
    mamori_state,
)
from ..contract import as_document, schema
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
    route.add_argument("prompt", help="the prompt. Use - to read standard input.")
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
    commands.add_parser("schema", help="the JSON contract `route --json` writes")
    commands.add_parser("algorithms", help="what can sit behind each port, and what each one costs")
    commands.add_parser("doctor", help="what is available, and what a missing piece costs")
    commands.add_parser("demo", help="a few prompts through the router")

    evaluate = commands.add_parser("eval", help="run the labelled corpus and report")
    evaluate.add_argument(
        "--source", help="only cases from this source, e.g. generated, borrowed:mamori"
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
    return sys.stdin.read() if prompt == "-" else prompt


def cmd_schema(out: TextIO) -> int:
    """The contract, from the installed package.

    Printed rather than linked, because a consumer generating code from it
    should be reading the one in the wheel they have and not the one on a branch
    somebody is editing.
    """
    print(json.dumps(schema(), ensure_ascii=False, indent=2), file=out)
    return EXIT_OK


def cmd_route(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    router: PromptRouter = config.router()
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
    """No model. Ever. ADR-0007."""
    cases = load_corpus()
    if args.source:
        cases = tuple(case for case in cases if case.source == args.source)
        if not cases:
            print(f"no cases from source {args.source!r}", file=out)
            return EXIT_ERROR
    report = run_evaluation(config.router(), cases)
    print(report.render(), file=out)
    return EXIT_OK


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
            return cmd_schema(stream)
        if args.command == "algorithms":
            return cmd_algorithms(config, stream)
        if args.command == "doctor":
            return cmd_doctor(config, stream)
        if args.command == "demo":
            return cmd_demo(config, stream)
        if args.command == "eval":
            return cmd_eval(args, config, stream)
    except IriguchiError as failure:
        print(f"iriguchi: {failure}", file=sys.stderr)
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
