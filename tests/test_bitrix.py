from __future__ import annotations

import pytest

from win_timer_app.bitrix import Bitrix24Client, Bitrix24Error, looks_like_webhook
from win_timer_app.controller import AppController


class FakeBx:
    """Stand-in for fast_bitrix24.Bitrix with the same get_all() contract."""

    def __init__(self, url, *, profile=None, error=None):
        self.url = url
        self._profile = profile if profile is not None else {"NAME": "Иван"}
        self._error = error
        self.calls = []

    def get_all(self, method, params=None):
        self.calls.append((method, params))
        if self._error is not None:
            raise self._error
        if method == "profile":
            return self._profile
        return {}


def _client(url="https://acme.bitrix24.ru/rest/1/abc/", **kwargs):
    fake = FakeBx(url, **kwargs)
    return Bitrix24Client(url, client_factory=lambda u: fake), fake


# --- looks_like_webhook ------------------------------------------------------

def test_looks_like_webhook_accepts_valid_rest_url():
    assert looks_like_webhook("https://acme.bitrix24.ru/rest/1/abc123/")


def test_looks_like_webhook_accepts_url_without_trailing_slash():
    assert looks_like_webhook("https://acme.bitrix24.ru/rest/12/abc123")


def test_looks_like_webhook_rejects_empty():
    assert not looks_like_webhook("")


def test_looks_like_webhook_rejects_non_https():
    assert not looks_like_webhook("http://acme.bitrix24.ru/rest/1/abc123/")


def test_looks_like_webhook_rejects_non_rest_url():
    assert not looks_like_webhook("https://acme.bitrix24.ru/company/")


# --- Bitrix24Client ----------------------------------------------------------

def test_client_rejects_invalid_webhook():
    with pytest.raises(Bitrix24Error):
        Bitrix24Client("not-a-url")


def test_test_connection_returns_profile():
    client, fake = _client(profile={"NAME": "Иван", "LAST_NAME": "Петров"})
    result = client.test_connection()
    assert result["NAME"] == "Иван"
    assert ("profile", None) in fake.calls


def test_test_connection_propagates_error():
    client, _ = _client(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        client.test_connection()


def test_real_client_constructs_in_worker_thread_without_event_loop():
    """Regression: the real fast-bitrix24 client builds asyncio primitives at
    construction time, which need a current event loop (Python 3.9). Built in a
    worker thread (e.g. QThread) with no loop, this raised
    'There is no current event loop'. The client must set one up itself.
    """
    import threading

    pytest.importorskip("fast_bitrix24")
    errors = []

    def worker():
        try:
            # default factory -> real fast_bitrix24.Bitrix (offline construction)
            Bitrix24Client("https://acme.bitrix24.ru/rest/1/abc/")._client()
        except Exception as exc:  # noqa: BLE001 - we assert on the captured error
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert not errors, f"construction failed in worker thread: {errors!r}"


# --- controller persistence --------------------------------------------------

def test_bitrix_webhook_defaults_empty(controller):
    assert controller.bitrix_webhook() == ""


def test_set_bitrix_webhook_trims_and_roundtrips(controller):
    controller.set_bitrix_webhook("  https://acme.bitrix24.ru/rest/1/abc/  ")
    assert controller.bitrix_webhook() == "https://acme.bitrix24.ru/rest/1/abc/"


def test_bitrix_webhook_persists_across_reload(storage):
    first = AppController(storage)
    first.set_bitrix_webhook("https://acme.bitrix24.ru/rest/1/abc/")
    second = AppController(storage)
    assert second.bitrix_webhook() == "https://acme.bitrix24.ru/rest/1/abc/"
