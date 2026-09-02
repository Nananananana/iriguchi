# 15. What "zero runtime dependencies" promises, and what it does not

**Status:** accepted

## Context

The README says it plainly, and it is the sentence people quote:

> **Zero runtime dependencies.** A tool that sees every prompt you type is a
> tool whose dependency list is a threat model. There isn't one, and CI checks
> that by installing the wheel with no extras and asserting nothing came along.

Every word of that is true and a job proves it. **It is also a promise about one
graph and not the other**, and nothing has ever said which.

v0.3 is where the difference becomes visible. The tray, the hotkey and the popup
go behind `tkinter`, and `tkinter` is not one thing:

| | Windows, macOS | Debian, Ubuntu, Fedora, Alpine |
|---|---|---|
| ships with CPython | yes | **no — `python3-tk` is a separate OS package** |
| `pip install iriguchi` pulls it | no | no |
| the install succeeds | yes | **yes** |
| a tray build starts | yes | **no** |

Measured rather than assumed. With the import blocked, what a person without
`python3-tk` gets is:

    ModuleNotFoundError: No module named 'tkinter'

That arrives **after** a successful install, from a tool that advertises having
no dependencies, and it reads as a broken package rather than as a missing OS
component. It is the worst available shape for that message.

There is a third state as well, and it is not a variant of the second. `tkinter`
can import perfectly on a headless machine — a server, a container, an SSH
session — and `Tk()` still fails, because there is no display. **Importable and
unusable are different facts about different problems**, which is the same
three-state shape `mamori_state()` already uses for the sibling:

    ABSENT       python3-tk is not installed
    BROKEN       importable, and no display to open a window on
    AVAILABLE    a window can be created

## Decision

**The promise stands unchanged in substance and gains one clause: it is about
the Python dependency graph.**

`pip install iriguchi` will keep pulling nothing, on every platform, and the
wheel job will keep proving it. What is being written down is the boundary
nobody had stated:

- **What it covers.** Nothing arrives in the environment alongside iriguchi.
  There is no third-party code in the import graph of any decision, and the
  dependency list a person has to audit is empty.
- **What it does not cover.** Whether the platform already has the pieces of
  the standard library iriguchi uses. `tkinter` is standard library and is
  absent from a stock Debian Python. So is `sqlite3` on a minimal build, for
  that matter — nothing here uses it, and the same argument would apply.

**A tray build must degrade rather than crash**, and it must say which of the
three states it found. A `ModuleNotFoundError` at start-up is the same defect
as the one ADR-0005 refused for mamori: *printing "not installed" for something
they already have tells somebody to install what they have.* Reversed here — a
traceback about a missing module tells somebody their install is broken, when
the fix is one `apt install python3-tk`.

**A GUI extra is refused.** `pip install iriguchi[gui]` cannot install
`python3-tk`, because pip does not install OS packages; an extra would be a
declaration that resolves to nothing and reassures the reader that the problem
is handled. That is worse than no extra at all.

### What CI does about it now

A step in the wheel job **reports** whether `tkinter` imports and whether a
window can be created, and reports the three states by name. It does not assert.

That distinction is the point. Asserting would either fail the build over
something no shipped code touches, or pin an expectation nobody has argued for.
Reporting turns "what does the runner have" from a belief into a line in a log,
**before** v0.3 is designed around a guess. The v0.1 pattern for exactly this is
`iriguchi doctor`, which says what is available and what a missing piece costs.

## Consequences

`iriguchi doctor` gains a fourth line when v0.3 starts, and it is the same shape
as the mamori line: three states, each with what it costs and what fixes it.

The README sentence gets its clause. It is a small edit and it is the whole
value of this ADR — a reader auditing a dependency list learns that the list is
empty *and* that emptiness is not the same as portability.

The CLI is unaffected and stays the fallback. Somebody on a headless box gets
`iriguchi route` and `iriguchi ask` and no tray, which is a smaller product
rather than a broken one.

## What it costs

**A platform matrix that the current CI does not have.** Nothing here runs on a
Debian image without `python3-tk`, so the state this ADR is most concerned about
is the one least tested. The reporting step narrows that — it will say what the
GitHub Ubuntu image has — but a runner image is not a stock Debian, and one
observation of one image is not a portability claim.

**The third state was untested on this machine, and the reporting step measured
it within minutes of being added.** `Tk()` succeeds here because there is a
display; the Ubuntu runner has none. From the first run of the job:

    tkinter importable: True
      Tcl/Tk 8.6
      importable and no display: TclError: no display name and no $DISPLAY
      -> the third state: installed, imports, cannot open a window

So the GitHub Ubuntu image has `tkinter` -- which means **the `ABSENT` case is
still the untested one**, and the runner cannot produce it. That is the same
shape as the `cp932` finding one file over: more runners of the same kind do not
make a machine capable of a failure.

What it does settle is the shape of `BROKEN`: a `TclError` carrying a readable
sentence, catchable, and distinguishable from an import failure by its type. A
tray build can name the state rather than guessing at it, and this paragraph was
written to say that was unknown.
