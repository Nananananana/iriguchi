# Architecture decision records

One file per decision that changed a boundary, a default, or a security
property. Each says what the situation was, what was chosen, what follows from
it, and — the part that is usually missing — what it costs.

What is *intended* next, and why, is in
[docs/proposals](../proposals/0001-the-design.md) instead: ADRs record decisions
already made, and a plan is neither.

These ten were written before the first line of code. That is legitimate — a
decision that has been made can be recorded whether or not it has been
implemented — and it is the reason the first commit can be reviewed at all. What
is *not* legitimate, and is why there is no `architecture.md` yet, is a
current-state document for code that does not exist.

| # | Decision |
|---|---|
| [0001](0001-the-domain-depends-on-nothing.md) | The domain depends on nothing, and does no I/O |
| [0002](0002-fail-closed.md) | Fail closed: doubt routes local, and local-impossible refuses |
| [0003](0003-sensitivity-is-a-veto.md) | Sensitivity is a veto, complexity is a preference, and they are never one score |
| [0004](0004-decide-before-the-request.md) | The decision is made before the request, from query features, by rules |
| [0005](0005-detection-is-a-port.md) | Detection is a port, mamori is its adapter, and the fallback errs toward local |
| [0006](0006-every-decision-carries-its-reasons.md) | Every decision carries its reasons to the end |
| [0007](0007-the-corpus-calls-no-model.md) | The evaluation corpus calls no model, and the traps are the dataset |
| [0008](0008-the-invariant-is-the-warm-path.md) | The performance invariant is the warm path, measured |
| [0009](0009-tsumugi-is-read-as-json.md) | tsumugi is read as JSON, and never imported |
| [0010](0010-the-layering-is-a-test.md) | The layering is a test |
