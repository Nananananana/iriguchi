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
configured timeout above thirty was silently discarded -- and **the symptom was
silence**, because the pass degraded to nothing. That is the bug worth carrying
forward. See `DEFAULT_TIMEOUT` for where the number came from and for what it
is not.

**Nothing is retried**, and the reason depends on a setting this module does not
send. See `TEMPERATURE_IS_THE_SERVERS`.

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

__all__ = [
    "DEFAULT_TIMEOUT",
    "MAX_RESPONSE_BYTES",
    "PERMITTED_SCHEMES",
    "RETRY_WOULD_NEED_A_KNOWN_TEMPERATURE",
    "UNRECORDED_TEMPERATURE",
    "OpenAICompatibleModel",
]

#: `urlopen` is a URL opener, not an HTTP client: given `file:///etc/passwd`
#: it reads the file, and `ftp:` and `data:` are handlers too. A base URL is
#: configuration, and configuration is where a typo lives -- so the schemes are
#: an allow-list rather than a deny-list, checked once at construction where a
#: person can be told, instead of at send time where they get a parse error
#: about a body.
PERMITTED_SCHEMES = frozenset({"http", "https"})

#: Seconds. **A ceiling, not a representative figure**, and the difference is
#: the whole of what this comment is for.
#:
#: It was derived from 345 seconds, which mamori saw for a 14B model here. That
#: number is one observation and it is the product of two faults: CPU inference,
#: because the CUDA runner was broken, and three models fighting over a 16 GB
#: card under ollama's five-minute keep-alive. It is not a property of a 14B
#: model. bench measured the same class of model properly afterwards:
#:
#:     14B q4  GPU   4.8 s/document (en)   5.4 s/document (ja)
#:     14B q4  CPU   49.0 s/document (en)  63.9 s/document (ja)
#:
#: So 345 is five to seven times the honest CPU figure and seventy times the GPU
#: one, and 600 has far more headroom than it looked like it had.
#:
#: **Kept anyway.** A ceiling that is too high costs a person who is already
#: stuck some waiting; a ceiling that is too low turns "this hardware is slow"
#: into "this model is broken", silently, which is the failure mamori actually
#: hit. Being wrong in the generous direction is the cheap side of this trade.
#:
#: What would change it is a measurement of the *longest* honest answer rather
#: than the typical one, on the slowest supported path. That does not exist.
DEFAULT_TIMEOUT = 600.0

#: What `sampling` says when nothing set a temperature.
#:
#: An earlier version of this file recorded the same fact as
#: `TEMPERATURE_IS_THE_SERVERS = True`, which **names the thing it does not
#: record**: it says whose setting decided and never what the setting was.
#: bench spotted it as the shape tsumugi lost twenty cases to -- `origin:
#: drafted`, with nothing anywhere saying drafted *by what*.
#:
#: iriguchi cannot know a server's default without asking, and asking is a
#: request it has no reason to make. So the honest value is the word, not a
#: silence and not a guess: **the temperature was the server's, and this
#: process did not observe it.**
UNRECORDED_TEMPERATURE = "the server's default, unrecorded"

#: Why the retry decision rests on the weaker of two arguments.
#:
#: The weaker one is iriguchi's and holds regardless: a retry multiplies a
#: timeout, and mamori's three thirty-second attempts plus backoff came to
#: ninety-seven, which looked exactly like a model too slow for the hardware and
#: was not. One attempt reported honestly beats three averaged into a shrug.
#:
#: The stronger one is bench's and is conditional: **at temperature 0 a failure
#: is not transient.** They measured llama3.1:8b returning a repetition loop in
#: seven of eight documents under greedy decoding, where a retry is an operation
#: that reliably obtains the same failure again -- leaving change the prompt,
#: change the model, or accept the loss, and retry is not among them.
#:
#: It does not apply whenever `temperature` is left unset, which is the default
#: here, because then the server decides and a failure may well be transient.
RETRY_WOULD_NEED_A_KNOWN_TEMPERATURE = True

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
        temperature: float | None = None,
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
        # `None` means the field is not sent at all, which is not the same as
        # sending a default -- the server's own configuration then applies and
        # this process never learns what it was. `sampling` is where that gets
        # said out loud.
        self._temperature = temperature

    @property
    def name(self) -> str:
        """Model and host, because either alone is ambiguous.

        The same model name answers from this machine and from a vendor, and
        before anything is sent that is the only distinction that matters.
        """
        return f"{self._model} at {self._base_url}"

    @property
    def sampling(self) -> str:
        """What decided the randomness, for a report to quote.

        A comparison that does not state this is a comparison nobody can
        repeat, and bench's arithmetic says why it matters at this corpus size:
        **21 cases, so one band changing is 4.76 points.** If sampling can move
        a single case, the noise floor is about five points and a difference
        under fifteen cannot be read.
        """
        if self._temperature is None:
            return UNRECORDED_TEMPERATURE
        return f"temperature {self._temperature:g}"

    def answer(self, prompt: str) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if self._temperature is not None:
            payload["temperature"] = self._temperature
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
                "timeout and not an answer. A 14B model here has been measured at "
                "about 5s per document on the GPU and 50-64s on the CPU, so a wait "
                "this long usually means the request never reached a model rather "
                "than that the model was slow."
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
