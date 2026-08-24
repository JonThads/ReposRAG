from unittest.mock import MagicMock

import httpx
import pytest

from api import generation


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # Retries would otherwise really sleep (with exponential backoff).
    monkeypatch.setattr(generation.time, "sleep", lambda seconds: None)


def _fake_client_factory(responses_or_exceptions):
    """
    Returns a callable matching `httpx.Client(timeout=...)` whose `.post()`
    yields the given sequence of return values / exceptions, one per call.
    """
    calls = iter(responses_or_exceptions)

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json):
            item = next(calls)
            if isinstance(item, Exception):
                raise item
            return item

    return lambda *args, **kwargs: FakeClient()


def _fake_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"response": text}
    return resp


def test_generate_answer_succeeds_without_retry(monkeypatch):
    monkeypatch.setattr(generation.httpx, "Client", _fake_client_factory([_fake_response("hi there")]))

    answer, elapsed = generation.generate_answer("q", [])

    assert answer == "hi there"
    assert elapsed >= 0


def test_generate_answer_retries_on_transient_timeout_then_succeeds(monkeypatch):
    monkeypatch.setattr(
        generation.httpx,
        "Client",
        _fake_client_factory([httpx.ConnectTimeout("boom"), _fake_response("recovered")]),
    )
    fake_counter = MagicMock()
    monkeypatch.setattr(generation.metrics, "OLLAMA_RETRIES", fake_counter)

    answer, _ = generation.generate_answer("q", [])

    assert answer == "recovered"
    fake_counter.inc.assert_called_once()


def test_generate_answer_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(generation.settings, "ollama_max_retries", 2)
    monkeypatch.setattr(
        generation.httpx,
        "Client",
        _fake_client_factory(
            [httpx.ConnectTimeout("1"), httpx.ConnectTimeout("2"), httpx.ConnectTimeout("3")]
        ),
    )

    with pytest.raises(httpx.ConnectTimeout):
        generation.generate_answer("q", [])


def test_generate_answer_does_not_retry_non_transient_errors(monkeypatch):
    class BoomError(Exception):
        pass

    monkeypatch.setattr(generation.httpx, "Client", _fake_client_factory([BoomError("not retryable")]))

    with pytest.raises(BoomError):
        generation.generate_answer("q", [])
