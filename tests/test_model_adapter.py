"""The adapter that answers, and the four things it must never do.

It must not open something that is not an HTTP URL, it must not lose the path
segment a person configured, it must not return a failure as a string, and it
must not put the prompt or the key into a message.

Nothing here reaches a network. The suite's autouse fixture replaces
`socket.socket` with a raiser, so a test that accidentally does a real request
fails rather than passing slowly -- and `test_the_suite_cannot_reach_a_network`
below checks that this adapter in particular is inside that fence, because an
adapter written after the fence went up is exactly the one nobody re-checked.
"""

from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Iterator
from typing import Any

import pytest

from iriguchi.errors import ModelError
from iriguchi.infrastructure.models.openai_compatible import (
    DEFAULT_TIMEOUT,
    MAX_RESPONSE_BYTES,
    PERMITTED_SCHEMES,
    OpenAICompatibleModel,
)
from iriguchi.ports.model import Model

SECRET = "sk-do-not-print-this-anywhere"
PROMPT = "田中太郎さんの住所は東京都港区1-2-3です"


class _Response(io.BytesIO):
    """Enough of an HTTP response for `with urlopen(...) as r: r.read(n)`."""

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _answering(content: Any) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """Capture the request instead of making it."""
    captured: list[Any] = []

    def fake_urlopen(request: Any, timeout: float | None = None) -> _Response:
        captured.append((request, timeout))
        return _Response(_answering("an answer"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    yield captured


class TestItIsAnHttpClientAndNotAUrlOpener:
    """`urlopen` reads a `file:` URL off the disk and hands it back.

    A base URL is configuration, and configuration is where a typo lives. The
    check is an allow-list at construction rather than a deny-list at send
    time, so a person is told about their setting instead of receiving a parse
    error about a body.
    """

    @pytest.mark.parametrize(
        "url",
        ["file:///etc/passwd", "ftp://host/x", "data:text/plain,hello", "", "not a url"],
    )
    def test_a_scheme_that_is_not_http_is_refused(self, url: str) -> None:
        with pytest.raises(ModelError, match="HTTP client"):
            OpenAICompatibleModel(url, "a-model")

    @pytest.mark.parametrize("url", ["http://127.0.0.1:11434/v1", "https://api.example.com/v1"])
    def test_http_and_https_are_permitted(self, url: str) -> None:
        assert OpenAICompatibleModel(url, "a-model").name.endswith("/")

    def test_the_permitted_set_is_exactly_two(self) -> None:
        """A third would need an argument. This asserts nobody added one quietly."""
        assert {"http", "https"} == PERMITTED_SCHEMES


class TestTheUrlItActuallyRequests:
    def test_a_base_without_a_trailing_slash_keeps_its_path(self, sent: list[Any]) -> None:
        """`urljoin` drops the last segment without one.

        `http://host/v1` + `chat/completions` is `http://host/chat/completions`,
        which is a 404 from a server that is working perfectly, and the person
        configured the URL correctly.
        """
        OpenAICompatibleModel("http://host/v1", "m").answer("hello")
        assert sent[0][0].full_url == "http://host/v1/chat/completions"

    def test_a_base_with_one_is_not_doubled(self, sent: list[Any]) -> None:
        OpenAICompatibleModel("http://host/v1/", "m").answer("hello")
        assert sent[0][0].full_url == "http://host/v1/chat/completions"


class TestTheTimeout:
    def test_the_default_is_not_thirty_seconds(self) -> None:
        """mamori's was, and took the smaller of two, so a configured value
        above it was silently discarded. On this hardware a 14B model answered
        in 345 seconds once that stopped happening -- the difference between a
        model tier working and one that never answers."""
        assert DEFAULT_TIMEOUT >= 345.0

    def test_it_is_the_one_passed_to_urlopen(self, sent: list[Any]) -> None:
        """Not a minimum of this and something else. That is the whole bug."""
        OpenAICompatibleModel("http://host/v1", "m", timeout=900.0).answer("hello")
        assert sent[0][1] == 900.0

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_a_nonpositive_timeout_is_refused(self, bad: float) -> None:
        with pytest.raises(ModelError, match="positive"):
            OpenAICompatibleModel("http://host/v1", "m", timeout=bad)


class TestEveryFailureRaises:
    """Never an empty string. At the call site "the model said nothing" and
    "the model could not be reached" are the same value unless one raises."""

    @staticmethod
    def _failing(exception: BaseException) -> Any:
        def fake(request: Any, timeout: float | None = None) -> _Response:
            raise exception

        return fake

    @pytest.mark.parametrize(
        ("exception", "expected"),
        [
            (
                urllib.error.HTTPError("http://host/v1", 503, "busy", {}, None),  # type: ignore[arg-type]
                "503",
            ),
            (TimeoutError(), "timeout"),
            (urllib.error.URLError("connection refused"), "could not be reached"),
            (OSError("no route to host"), "could not be reached"),
        ],
        ids=["an error status", "a timeout", "an unreachable host", "an OS error"],
    )
    def test_a_transport_failure_becomes_a_model_error(
        self, monkeypatch: pytest.MonkeyPatch, exception: BaseException, expected: str
    ) -> None:
        monkeypatch.setattr("urllib.request.urlopen", self._failing(exception))
        with pytest.raises(ModelError, match=expected):
            OpenAICompatibleModel("http://host/v1", "m").answer(PROMPT)

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            (b"<html>a gateway page</html>", "not JSON"),
            (b'{"error": "no"}', "choices"),
            (b'{"choices": []}', "choices"),
            (json.dumps({"choices": [{"message": {"content": None}}]}).encode(), "not a string"),
            (json.dumps({"choices": [{"message": {"content": 7}}]}).encode(), "not a string"),
        ],
        ids=["html", "an error object", "no choices", "a null content", "a numeric content"],
    )
    def test_a_body_it_cannot_read_becomes_a_model_error(
        self, monkeypatch: pytest.MonkeyPatch, body: bytes, expected: str
    ) -> None:
        monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Response(body))
        with pytest.raises(ModelError, match=expected):
            OpenAICompatibleModel("http://host/v1", "m").answer(PROMPT)

    def test_an_oversized_body_is_refused_rather_than_buffered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oversized = b"x" * (MAX_RESPONSE_BYTES + 1)
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda request, timeout=None: _Response(oversized)
        )
        with pytest.raises(ModelError, match="Refused"):
            OpenAICompatibleModel("http://host/v1", "m").answer("hello")

    def test_an_empty_answer_is_an_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A model that legitimately says nothing is not a failure, and this is
        the reason failures must raise: the return value is already taken."""
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda request, timeout=None: _Response(_answering(""))
        )
        assert OpenAICompatibleModel("http://host/v1", "m").answer("hello") == ""


class TestNothingLeaksIntoAMessage:
    """The router's whole purpose. A component that prints what it was
    protecting has undone the thing it is part of."""

    @staticmethod
    def _raising(exception: BaseException) -> Any:
        def fake(request: Any, timeout: float | None = None) -> _Response:
            raise exception

        return fake

    @pytest.mark.parametrize(
        "exception",
        [
            urllib.error.HTTPError("http://host/v1", 500, "err", {}, None),  # type: ignore[arg-type]
            TimeoutError(),
            urllib.error.URLError("refused"),
        ],
        ids=["a status", "a timeout", "an unreachable host"],
    )
    def test_the_prompt_is_not_in_the_failure(
        self, monkeypatch: pytest.MonkeyPatch, exception: BaseException
    ) -> None:
        monkeypatch.setattr("urllib.request.urlopen", self._raising(exception))
        model = OpenAICompatibleModel("http://host/v1", "m", api_key=SECRET)
        with pytest.raises(ModelError) as raised:
            model.answer(PROMPT)
        assert PROMPT not in str(raised.value)
        assert "田中" not in str(raised.value)

    @pytest.mark.parametrize(
        "exception",
        [
            urllib.error.HTTPError("http://host/v1", 401, "unauthorized", {}, None),  # type: ignore[arg-type]
            urllib.error.URLError("refused"),
        ],
        ids=["a 401, where a key is most likely to be echoed", "an unreachable host"],
    )
    def test_the_api_key_is_not_in_the_failure(
        self, monkeypatch: pytest.MonkeyPatch, exception: BaseException
    ) -> None:
        monkeypatch.setattr("urllib.request.urlopen", self._raising(exception))
        model = OpenAICompatibleModel("https://api.example.com/v1", "m", api_key=SECRET)
        with pytest.raises(ModelError) as raised:
            model.answer("hello")
        assert SECRET not in str(raised.value)

    def test_the_api_key_is_not_in_the_name(self) -> None:
        """`name` is printed before every send, by design."""
        model = OpenAICompatibleModel("https://api.example.com/v1", "m", api_key=SECRET)
        assert SECRET not in model.name

    def test_an_error_bodys_contents_are_not_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A server's error body can quote the request back, and the request is
        the prompt. So the status is reported and nothing else is."""
        echoed = io.BytesIO(f"400: bad request: {PROMPT}".encode())
        failure = urllib.error.HTTPError("http://host/v1", 400, "bad", {}, echoed)  # type: ignore[arg-type]
        monkeypatch.setattr("urllib.request.urlopen", self._raising(failure))
        with pytest.raises(ModelError) as raised:
            OpenAICompatibleModel("http://host/v1", "m").answer(PROMPT)
        assert PROMPT not in str(raised.value)


class TestItIsWhatThePortAsksFor:
    def test_it_satisfies_the_protocol(self) -> None:
        assert isinstance(OpenAICompatibleModel("http://host/v1", "m"), Model)

    def test_the_name_says_model_and_host(self) -> None:
        """Either alone is ambiguous: the same model name answers from this
        machine and from a vendor, and that is the distinction that matters
        before something is sent."""
        name = OpenAICompatibleModel("http://127.0.0.1:11434/v1", "qwen2.5:14b").name
        assert "qwen2.5:14b" in name
        assert "127.0.0.1:11434" in name

    def test_the_key_goes_in_a_header_and_the_prompt_in_the_body(self, sent: list[Any]) -> None:
        model = OpenAICompatibleModel("https://api.example.com/v1", "m", api_key=SECRET)
        model.answer(PROMPT)
        request = sent[0][0]
        assert request.get_header("Authorization") == f"Bearer {SECRET}"
        assert json.loads(request.data)["messages"][0]["content"] == PROMPT
        assert json.loads(request.data)["stream"] is False


def test_the_suite_cannot_reach_a_network() -> None:
    """The fence, checked from inside the newest thing standing behind it.

    An adapter written after the fence went up is exactly the one nobody
    re-confirmed was covered, and this is the first component here that would
    genuinely open a socket.

    **It must surface as the fence's own error, not as a `ModelError`.** This
    adapter catches `OSError` and turns it into a `ModelError`, so a fence that
    raised one would be swallowed -- the test would pass, the message would read
    "could not be reached", and a real connection attempt would be
    indistinguishable from a blocked one. `conftest.NetworkAccessError` is an
    `AssertionError` for that reason, decided before this adapter existed, and
    this test is where the two meet.
    """
    from conftest import NetworkAccessError

    with pytest.raises(NetworkAccessError):
        OpenAICompatibleModel("http://127.0.0.1:1/v1", "m", timeout=1.0).answer("hello")
