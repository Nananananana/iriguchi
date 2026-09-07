# 21. A foreign exception message is unclassified text

**Status:** accepted

## Context

Two ADRs were each true and the join between them was not.

[ADR-0002](0002-fail-closed.md) turns a broken proposer into a decision: the
most restrictive route available, with a reason naming what broke. A scanner
that dies does not cost you your afternoon, it costs you the external route.

[ADR-0016](0016-a-decision-can-be-published-because-it-holds-no-prompt.md) says
that decision may be published — `route --json`, `iriguchi.routing-decision/1`,
read by Sora and put on a screen — **because it holds no prompt**. The argument
is short and was correct as far as it went:

    rule ids, source names, details   written by iriguchi, not by the prompt
    spans                             offsets into a prompt the reader lacks
    bands, scores, weights            arithmetic

The first line is the one that failed. `details` were not all written by
iriguchi. `PromptRouter._scanner_failed` interpolated `str(failure)`:

```python
detail = f"the sensitivity scanner {name!r} could not answer ({str(failure)}), ..."
```

and a scanner that quotes the text it choked on is not an unusual scanner. It
is the default behaviour of a regex engine, a tokenizer and a JSON parser:

    regex engine gave up on 'Please email tanaka@example.com the quarterly ...'

Measured on the real router before anything was changed. With a scanner raising
that message, `SECRET in route --json` was **True**, via
`reasons[].detail` of `routing.scanner-failed`. The same held for the
estimator's `routing.estimator-failed` and the cascade's `cascade.judge-failed`.

Two details make it worse rather than better.

**The guarantee rested on code this repository does not write.** iriguchi does
not author mamori's exception messages or presidio's, and the whole point of
[ADR-0005](0005-detection-is-a-port.md) is that a scanner is somebody else's.

**The docstring stated the invariant it was breaking.** `_scanner_failed` said
*it carries the scanner's failure and never the text* — which is one sentence
right up until a scanner puts the text in its failure, and then it is the bug
described in the present tense.

The tests were on the wrong side too. `test_the_failure_is_in_the_reasons_and_names_the_scanner`
asserted `"rule table did not load" in failure.detail`: the message, verbatim,
pinned in place.

## Decision

**A message may travel in a published decision only when whoever raised it said
it may.** `IriguchiError` carries `quotable`, default `False`, and
`errors.safe_detail` returns the message when it is set and the exception's
class name otherwise.

This is the rule iriguchi gave Sora for the same problem in the same week, in
[ADR-0020](0020-iriguchi-names-its-failures.md): **keep the name, discard the
sentence.** Sora folds failures on the name before the colon on stderr and
keeps nothing else, because stderr can quote what was handed in. A published
decision has exactly that property and had not been given exactly that rule.

**Why a flag and not a blanket redaction.** A class name alone would have
thrown away iriguchi's own diagnostics, and one of them is load-bearing:
`SuppliedScanner` says *which* supplied finding ran past the end of the prompt,
built from rule ids, spans and a length — precisely what
[ADR-0006](0006-every-decision-carries-its-reasons.md) permits to travel. The
distinction is not *who raised it* but *what the message was built from*, and
the only person in a position to know that is the one at the `raise`.

**Why the default is `False`.** The population that matters is exceptions
iriguchi did not write, and they have no flag. Fail closed
([ADR-0002](0002-fail-closed.md)) applied to a document rather than to a route.

## Consequences

**Two sites vouch, and a test lists them.** `SuppliedScanner`'s out-of-range
message and mamori's absent-sibling constant. An AST scan finds every
`quotable=` in `src/` and fails on one that is not on the list, so a third
becomes a deliberate act visible in a diff rather than a keyword argument
nobody reads.

**A reason still says what broke.** The component's name and the failure's real
class both survive — `RuntimeError` when an adapter raises one, not `ScanError`,
because telling somebody the scanner raised a `ScanError` when it did not sends
them to the wrong place. Redaction that leaves nothing behind would be a second
defect wearing the first one's clothes.

**The route is unchanged.** ADR-0002 has not been traded for ADR-0016: a broken
scanner still costs the external destination, and a test asserts it in the same
file as the redaction.

**What this does not fix.** `--explain --dry-run` prints the protected text on
purpose, and `ask` prints a model's answer. Both are content the person asked
to see on their own terminal, and neither is a published document. This decision
is about what iriguchi *hands to somebody else* while calling it prompt-free.

**How it was found.** Not by reading. A scanner was written that quotes its
input, and the published document was searched for the secret — the same method
that found the `--findings` span bug, the missing `__main__`, and the cp932
stdin failure. The code had been read several times with this invariant in mind
and reads correctly, because `str(failure)` looks like a diagnostic rather than
like an untrusted string.
