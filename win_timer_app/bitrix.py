"""Thin wrapper around fast-bitrix24 for talking to a Bitrix24 portal.

Keeps the rest of the app decoupled from the library: the UI/controller depend
on this small interface, and tests inject a fake client via ``client_factory``.
"""
from __future__ import annotations

import asyncio
import re
import warnings

# https://portal.bitrix24.ru/rest/<user_id>/<token>/
_WEBHOOK_RE = re.compile(r"^https://[^/\s]+/rest/\d+/[^/\s]+/?$")


def looks_like_webhook(url: str) -> bool:
    """Lightweight format check for an inbound-webhook URL (not a live check)."""
    return bool(_WEBHOOK_RE.match((url or "").strip()))


class Bitrix24Error(Exception):
    """Raised for configuration problems with the Bitrix24 client."""


def _ensure_event_loop() -> None:
    """Make sure the current thread has a usable asyncio event loop.

    fast-bitrix24's client builds asyncio primitives (``asyncio.Event``) at
    construction time, which require a current event loop in the calling thread
    (Python 3.9). Worker threads (e.g. a ``QThread``) have none, so create one.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("event loop is closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _default_factory(webhook_url: str):
    # Imported lazily so the module (and tests) don't require fast-bitrix24.
    from fast_bitrix24 import Bitrix

    return Bitrix(webhook_url)


class Bitrix24Client:
    def __init__(self, webhook_url: str, *, client_factory=None) -> None:
        url = (webhook_url or "").strip()
        if not looks_like_webhook(url):
            raise Bitrix24Error("Некорректный URL вебхука")
        self._webhook_url = url
        self._factory = client_factory or _default_factory
        self._bx = None

    def _client(self):
        if self._bx is None:
            _ensure_event_loop()
            self._bx = self._factory(self._webhook_url)
        return self._bx

    def test_connection(self) -> dict:
        """Call ``profile`` and return the current user's profile dict.

        Uses ``get_all`` because fast-bitrix24's ``call`` requires a non-empty
        item list; ``profile`` takes no parameters. ``get_all`` works for this
        single-object method and returns the profile dict, but warns that it is
        meant for list methods — we silence that one expected warning. Raises
        whatever the underlying client raises on failure.
        """
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, message="get_all")
            return self._client().get_all("profile")
