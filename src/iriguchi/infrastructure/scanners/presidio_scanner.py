"""Microsoft Presidio as a `SensitivityScanner`.

The second real answer to the built-in scanner's **61.7% miss rate**, and the
first one a user can actually install: `pip install "iriguchi[presidio]"`.
mamori is not on PyPI (`docs/feasibility.md` F2), so until it is, this is the
only way somebody who is not the author gets detection worth having.

Presidio is **MIT**, from Microsoft, and is the default answer in this space:
spaCy-backed NER for names, organisations and locations, plus pattern and
checksum recognisers for cards, IBANs and national ids, across a long list of
languages. It is a dependency worth taking.

**Optional, and it stays optional.** iriguchi's core still installs with
nothing. This module raises at *construction* rather than at import, so
`iriguchi doctor` can report Presidio as absent without the tool failing to
start -- the same shape as the mamori adapter, for the same reason.

## What is deliberately dropped at this boundary

`RecognizerResult.score` is a **confidence**, and a `Finding` has nowhere to put
one. That is not an oversight -- `interop/presidio.py` argues it at length: a
confidence on a veto becomes a threshold, and a threshold is a number somebody
lowers until the leak rate looks acceptable.

But Presidio's score is real, and discarding it silently would be worse than
using it, because Presidio deliberately emits low-confidence guesses it expects
the caller to filter. So the filtering happens **where the number means what it
says** -- `score_threshold` goes to Presidio's own analyzer, the knob its
authors documented -- and what crosses into iriguchi is a decision already made
rather than a number iriguchi would have to interpret.

`analysis_explanation` is dropped for the reason mamori's `preview` is: it
describes *how a value was found*, which is a statement about the value.

## It refuses to let Presidio reach the network

`AnalyzerEngine()` calls `_download_spacy_model_if_needed`, which calls
`spacy.cli.download`, which shells out and fetches **382MB** from GitHub. No
prompt, no flag, no way to see it coming from the constructor call.

For most libraries that is a convenience. For this one it is disqualifying:
iriguchi's whole claim is that the decision happens locally, before any request,
with nothing leaving the machine -- and a scanner that opens a connection while
being *built* has broken that before it reads a single prompt. On a metered
connection it is also 382MB somebody did not agree to.

So the model is checked with `spacy.util.is_package` **before** the engine is
constructed, and a missing one is a refusal naming the exact command. The
download still exists; it just belongs to the person, not to the router.

## Why the entity list is passed through rather than curated

Presidio ships recognisers nobody here has evaluated. Filtering them to a list
that looked sensible would be iriguchi quietly deciding that, say, a medical
licence number is not sensitive. The default is **everything Presidio reports**,
and `entities=` narrows it for somebody who has a reason.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence

from ...domain.sensitivity import Finding
from ...domain.span import Span
from ...errors import ScanError

__all__ = ["SOURCE", "PresidioScanner", "presidio_state"]

#: What a finding from this adapter says about where it came from. The same
#: string `interop/presidio.py` uses for findings a caller converted by hand, so
#: an explanation reads the same whether the analyzer ran here or over there.
SOURCE = "presidio"

#: Passed to Presidio's analyzer rather than applied here. Its authors document
#: this knob and its recognisers are calibrated against it; iriguchi has no
#: opinion about 0.5 and would only be inventing one.
DEFAULT_SCORE_THRESHOLD = 0.5

#: Presidio's default English model, and the one it would fetch on its own.
#: Named here so the refusal can print the exact command rather than a shape.
DEFAULT_MODEL = "en_core_web_lg"

_MISSING = (
    "presidio-analyzer is not installed. Install it with "
    '`pip install "iriguchi[presidio]"`, then fetch a spaCy model with '
    "`python -m spacy download en_core_web_lg`. Presidio would download that "
    "model itself, from a constructor, and iriguchi refuses to let it -- see "
    "the module docstring."
)


def presidio_state() -> tuple[bool, str]:
    """Whether Presidio can be used here, and what to say when it cannot.

    Answered with `find_spec` rather than by importing, because importing
    Presidio loads spaCy and a language model -- seconds of work and a few
    hundred megabytes for a question `doctor` asks on every run.
    """
    try:
        found = importlib.util.find_spec("presidio_analyzer")
    except (ImportError, ValueError) as failure:
        return False, f"looking for presidio-analyzer failed: {failure}"
    return (True, "") if found is not None else (False, _MISSING)


class PresidioScanner:
    """Presidio's analyzer, behind iriguchi's port.

    Args:
        language: Which language's recogniser registry to use. Presidio's
            registry is per-language, and a mismatch silently finds nothing --
            the worst failure mode a scanner has.
        entities: Restrict to these entity types. `None` means **everything
            Presidio reports**, which is the safe default for a veto; a curated
            list would be iriguchi deciding what is not sensitive.
        score_threshold: Passed to Presidio, where a confidence means what it
            says. Nothing downstream of this sees a number.
        model: The spaCy model Presidio will use. Verified present **before**
            the engine is built, because Presidio fetches a missing one over the
            network without asking.

    Raises:
        ScanError: at construction, when presidio-analyzer is absent, when
            the spaCy model is missing, or when the analyzer will not build.
            Construction rather than import, so `doctor` can report it without
            the CLI failing to start.
    """

    name = SOURCE

    def __init__(
        self,
        language: str = "en",
        entities: Sequence[str] | None = None,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        model: str = DEFAULT_MODEL,
    ) -> None:
        usable, detail = presidio_state()
        if not usable:
            raise ScanError(detail)
        self._refuse_if_presidio_would_download(model)
        try:
            from presidio_analyzer import AnalyzerEngine
        except Exception as failure:  # pragma: no cover - needs a broken install
            raise ScanError(
                f"presidio-analyzer is installed and will not import: "
                f"{type(failure).__name__}: {failure}. That is not the same as "
                f"it being absent."
            ) from failure
        try:
            self._engine = AnalyzerEngine()
        except Exception as failure:
            # Almost always the missing spaCy model, and the exception Presidio
            # raises for it is not one a person can act on without knowing that.
            raise ScanError(
                f"presidio-analyzer is installed and its analyzer would not build: "
                f"{type(failure).__name__}: {failure}. The usual cause is a missing "
                f"spaCy model -- try `python -m spacy download en_core_web_lg`."
            ) from failure
        self._language = language
        self._entities = list(entities) if entities is not None else None
        self._score_threshold = score_threshold

    @staticmethod
    def _refuse_if_presidio_would_download(model: str) -> None:
        """Check the spaCy model is here, before Presidio decides to fetch it.

        `AnalyzerEngine()` calls `spacy.cli.download` for a missing model: 382MB
        over the network, from a constructor, with nothing said. A router that
        promises to decide locally cannot let that happen by accident, and the
        person who wants the model can run one command.

        Checked with `is_package` rather than by loading, because loading is the
        expensive half and the question here is only whether it is installed.
        """
        try:
            import spacy
        except Exception as failure:  # pragma: no cover - presidio requires spacy
            raise ScanError(
                f"presidio-analyzer is installed and spaCy is not importable: "
                f"{type(failure).__name__}: {failure}"
            ) from failure
        if not spacy.util.is_package(model):
            raise ScanError(
                f"the spaCy model {model!r} is not installed. Presidio would "
                f"download it -- roughly 382MB, from a constructor, without "
                f"asking -- and iriguchi will not let it: this router decides "
                f"locally, and a scanner that opens a connection while being "
                f"built has broken that before reading a prompt. Run "
                f"`python -m spacy download {model}` and try again."
            )

    def scan(self, text: str) -> tuple[Finding, ...]:
        """What Presidio objects to in `text`, as findings.

        Raises:
            ScanError: when the analyzer fails. Raised rather than returning
                nothing, because a scanner reporting no findings after it broke
                is a veto that quietly stopped working. ADR-0002 turns this into
                the most restrictive route with a reason that says so.
        """
        try:
            results = self._engine.analyze(
                text=text,
                language=self._language,
                entities=self._entities,
                score_threshold=self._score_threshold,
            )
        except Exception as failure:
            raise ScanError(
                f"presidio-analyzer failed on this prompt: {type(failure).__name__}: {failure}"
            ) from failure

        # Sorted by offset, so two runs over one prompt produce the same
        # explanation. Presidio returns recogniser order, which is not a promise
        # it makes.
        return tuple(
            sorted(
                (
                    Finding(
                        rule=f"{SOURCE}.{result.entity_type.lower()}",
                        source=SOURCE,
                        span=Span(int(result.start), int(result.end)),
                    )
                    for result in results
                ),
                key=lambda finding: (finding.span.start, finding.span.end, finding.rule),
            )
        )
