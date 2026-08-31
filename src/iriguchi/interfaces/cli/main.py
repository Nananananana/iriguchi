"""The command line. The composition root, and the only place adapters are named.

Six commands, and `route` is the one the project is named after.

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
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import TextIO

from ...application.routing import PromptRouter
from ...config import IriguchiConfig
from ...domain.destination import Destination, Route
from ...errors import EscalationRefusedError, IriguchiError
from ...evaluation.dataset import load_corpus
from ...evaluation.scoring import run as run_evaluation
from ...infrastructure.scanners.mamori_scanner import (
    SiblingState,
    mamori_is_available,
    mamori_state,
)
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
        choices=("fallback", "mamori"),
        default=None,
        help=(
            "which sensitivity scanner to use. Defaults to the built-in fallback even "
            "when mamori is installed: changing the scanner changes what leaves this "
            "machine, and that is not a thing to inherit from what happens to be on "
            "the system."
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
        use_mamori=args.scanner == "mamori",
    )


def _read(prompt: str) -> str:
    return sys.stdin.read() if prompt == "-" else prompt


def cmd_route(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    router: PromptRouter = config.router()
    prompt = _read(args.prompt)
    decision = router.route(prompt, config.available)

    print(render_decision(decision, verbose=args.explain), file=out)
    if args.explain and decision.route is Route.EXTERNAL:
        print(_what_would_leave(config, prompt), file=out)
    return EXIT_REFUSED if decision.route is Route.REFUSED else EXIT_OK


def cmd_ask(args: argparse.Namespace, config: IriguchiConfig, out: TextIO) -> int:
    """The only command that sends, and the only one that can be wrong twice.

    A refusal is printed and nothing runs. Everything else prints the route
    first, then the answer -- in that order on purpose, so that a person reading
    a terminal sees where their words went before they see what came back.
    """
    from ...application.asking import Asker

    prompt = _read(args.prompt)
    asker = Asker(
        router=config.router(),
        local=config.local_answerer() if config.local else None,
        external=config.external_answerer() if config.external else None,
        channel=config.channel() if config.external else None,
    )

    if args.dry_run:
        decision = asker.router.route(prompt, config.available)
        print(render_decision(decision, verbose=args.explain), file=out)
        if decision.route is Route.EXTERNAL:
            print(_what_would_leave(config, prompt), file=out)
        print("\nNothing was asked. Drop --dry-run to send it.", file=out)
        return EXIT_REFUSED if decision.route is Route.REFUSED else EXIT_OK

    answer = asker.ask(prompt, config.available)
    print(render_decision(answer.decision, verbose=args.explain), file=out)
    if not answer.answered:
        return EXIT_REFUSED

    # ADR-0013: iriguchi only escalates when its own scanner said CLEAR, so
    # anything mamori protected on the way out is something the scanner missed.
    # Printed before the answer, because it is about the decision rather than
    # about the reply, and a person scrolling to the answer would never see it
    # underneath.
    for missed in answer.missed:
        print(f"\n  missed by the scanner  {missed.detail}", file=out)

    print(f"\n{answer.model} answered:\n", file=out)
    print(answer.text, file=out)
    return EXIT_OK


def _what_would_leave(config: IriguchiConfig, prompt: str) -> str:
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
        return f"\n  would leave    (cannot say: {refused})"

    try:
        escalation = channel.prepare(prompt)
    except EscalationRefusedError as refused:
        # Not a crash and not a downgrade. The route stands; the protection
        # that route depends on refused, and the person needs to know which.
        return f"\n  would leave    nothing -- the escalation was refused:\n      {refused}"

    try:
        lines = ["", "  would leave", f"    {escalation.protected_text}"]
        if escalation.findings:
            lines.append("")
            lines.append("  and the scanner had missed")
            lines.extend(
                f"    {finding.rule:<40}{finding.detail}" for finding in escalation.findings
            )
        return "\n".join(lines)
    finally:
        escalation.close()


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
    if config.use_mamori:
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
        lines.append(
            "note: the built-in scanner over-detects on purpose and misses names "
            "without an honorific, English names, company names and addresses "
            "entirely. Install mamori for a scanner that does not, and see "
            "docs/measurements.md for the number."
        )
    print("\n".join(lines), file=out)
    return EXIT_OK


def cmd_demo(config: IriguchiConfig, out: TextIO) -> int:
    router = config.router()
    for prompt in DEMO_PROMPTS:
        print(f"\n$ iriguchi route {prompt!r}\n", file=out)
        decision = router.route(prompt, config.available)
        print(render_decision(decision), file=out)
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
