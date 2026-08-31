"""One adapter for every server that speaks `/v1/chat/completions`.

Ollama, llama.cpp's server, vLLM, LM Studio, and the hosted APIs all expose it.
mamori chose this shape over any single vendor's SDK and the reason transfers:
one adapter covers the local model and the upstream, and **the difference
between them is a hostname**.

Written against `urllib`, because iriguchi installs with no runtime dependencies
and that promise has a CI job behind it.

Three decisions here are worth reading before changing anything, and two come
from a mistake mamori made and then measured.

**The timeout is honoured, not minimised.** mamori had a request default of
thirty seconds and took the smaller of the request's and the endpoint's, so a
configured timeout above thirty was silently discarded. On hardware where a
local model needs minutes for a document, that is the difference between a model
tier working and one that never answers. `DEFAULT_TIMEOUT` is 600 seconds here
because **mamori measured 345** for a 14B model on this machine, and a figure
with headroom over a measurement is a different thing from a figure somebody
liked the look of.

**Nothing is retried.** A retry multiplies a timeout, and mamori's three
attempts of thirty seconds plus backoff came to ninety-seven -- which looked
exactly like a model too slow for the hardware, and was not. Until iriguchi can
tell "the server is loading weights" from "this model cannot answer in the time
allowed", one attempt reported honestly is worth more than three averaged into a
shrug. Named as a v0.3 item rather than left as an omission.

**A failure raises.** Never an empty string, never a partial answer. At the call
site "the model said nothing" and "the model could not be reached" are
indistinguishable unless one of them raises -- the same ambiguity `ScanError`
exists to prevent one layer up.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from ...errors import ModelError

__all__ = ["DEFAULT_TIMEOUT", "MAX_RESPONSE_BYTES", "PERMITTED_SCHEMES", "OpenAICompatibleModel"]

#: `urlopen` is a URL opener, not an HTTP client: given `file:///etc/passwd`
#: it reads the file, and `ftp:` and `data:` are handlers too. A base URL is
#: configuration, and configuration is where a typo lives -- so the schemes are
#: an allow-list rather than a deny-list, checked once at construction where a
#: person can be told, instead of at send time where they get a parse error
#: about a body.
PERMITTED_SCHEMES = frozenset({"http", "https"})

#: Seconds. Not thirty, and not a round number picked for looking reasonable.
#: mamori measured a 14B local model answering in 345 seconds on this hardware
#: once its timeout stopped being silently capped; this is that with room.
#:
#: A person waiting ten minutes for an answer has a problem. It is a different
#: problem from the one where the answer never arrives and nothing says why.
DEFAULT_TIMEOUT = 600.0

#: Bodies larger than this are refused rather than buffered. mamori dropped
#: their proxy's cap to 8 MB after finding that protecting a 534 KB document
#: peaks near a hundred times the size of the text. Nothing here protects, so
#: this bound is about a server that answers with a filesystem.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class OpenAICompatibleModel:
    """A chat completion, from anywhere that speaks the API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        api_key: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ModelError(f"timeout must be positive; got {timeout!r}")
        scheme = urlsplit(base_url).scheme.lower()
        if scheme not in PERMITTED_SCHEMES:
            raise ModelError(
                f"{base_url!r} uses the {scheme!r} scheme. This is an HTTP client, "
                f"not a URL opener: `urlopen` would read a `file:` URL off this "
                f"disk and hand it back as an answer. Permitted: "
                f"{sorted(PERMITTED_SCHEMES)}."
            )
        # `urljoin` drops the last path segment unless the base ends in a slash,
        # so `http://host/v1` would quietly become `http://host/chat/...`.
        self._base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self._model = model
        self._timeout = timeout
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Model and host, because either alone is ambiguous.

        The same model name answers from this machine and from a vendor, and
        before anything is sent that is the only distinction that matters.
        """
        return f"{self._model} at {self._base_url}"

    def answer(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # S310 is about `file:`, `ftp:` and friends reaching a URL opener. The
        # scheme was checked in `__init__` against `PERMITTED_SCHEMES`, which is
        # the fix rather than the suppression -- and it is checked there so a
        # person is told about their configuration instead of being handed a
        # parse error about a body.
        request = urllib.request.Request(  # noqa: S310
            urljoin(self._base_url, "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as failure:
            # The status and nothing else. An error body can quote the request
            # back, and the request holds the prompt.
            raise ModelError(
                f"{self.name} answered {failure.code}. Nothing from the body is "
                "reported: an error body can quote the request, and the request "
                "is the prompt."
            ) from failure
        except TimeoutError as failure:
            raise ModelError(
                f"{self.name} did not answer within {self._timeout:g}s. That is a "
                "timeout and not an answer -- a local model on this hardware has "
                "been measured at 345s, so a low limit reads as a broken model."
            ) from failure
        except (urllib.error.URLError, OSError) as failure:
            raise ModelError(f"{self.name} could not be reached: {failure}") from failure

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelError(
                f"{self.name} answered with more than {MAX_RESPONSE_BYTES} bytes. "
                "Refused rather than buffered."
            )
        return self._content(raw)

    def _content(self, raw: bytes) -> str:
        """The one string in the body, or a refusal naming what was wrong.

        Every branch raises rather than returning an empty string. A body this
        code did not understand and an answer of no words are different events,
        and a caller cannot tell them apart from a return value.
        """
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as failure:
            raise ModelError(f"{self.name} answered with something that is not JSON") from failure

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as failure:
            raise ModelError(
                f"{self.name} answered JSON without `choices[0].message.content`. "
                "What the body did contain is not reported -- a body that "
                "surprised this code is a body nothing has vetted."
            ) from failure

        if not isinstance(content, str):
            raise ModelError(f"{self.name} answered with a {type(content).__name__}, not a string")
        return content
