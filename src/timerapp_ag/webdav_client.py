"""Минимальный WebDAV-клиент на стандартной библиотеке."""
from __future__ import annotations

import base64
import os
import urllib.error
import urllib.request
from typing import Mapping

from .webdav_config import WebDavConfig


class WebDavError(Exception):
    """Ошибка WebDAV-запроса."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _sanitize_error(text: str, config: WebDavConfig) -> str:
    sanitized = text
    if config.password:
        sanitized = sanitized.replace(config.password, "***")
    if config.url:
        sanitized = sanitized.replace(config.url, "***")
    return sanitized


def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _timeout_seconds() -> float:
    raw = (os.environ.get("WEBDAV_TIMEOUT") or os.environ.get("BITRIX24_TIMEOUT") or "60").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 60.0


class WebDavClient:
    def __init__(self, config: WebDavConfig) -> None:
        if not config.is_configured():
            raise WebDavError("WebDAV не настроен: укажите URL и имя пользователя")
        self._config = config

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, bytes, Mapping[str, str]]:
        request_headers = {
            "Authorization": _basic_auth_header(self._config.username, self._config.password),
            "User-Agent": "TaskTimer-link-B24",
        }
        if headers:
            request_headers.update(headers)
        req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(req, timeout=_timeout_seconds()) as response:
                body = response.read()
                return response.status, body, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            message = body.decode("utf-8", errors="replace") or exc.reason or str(exc.code)
            raise WebDavError(
                _sanitize_error(f"WebDAV {method} {exc.code}: {message}", self._config),
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise WebDavError(_sanitize_error(f"WebDAV {method}: {exc.reason}", self._config)) from exc

    def test_connection(self) -> str:
        base = self._config.url.rstrip("/") + "/"
        self._request("HEAD", base)
        return "Подключение успешно"

    def exists(self, url: str | None = None) -> bool:
        target = url or self._config.remote_url()
        try:
            self._request("HEAD", target)
            return True
        except WebDavError as exc:
            if exc.status_code == 404:
                return False
            if exc.status_code in {405, 501}:
                return self._exists_via_get_probe(target)
            raise

    def _exists_via_get_probe(self, url: str) -> bool:
        """Fallback, если сервер не поддерживает HEAD (405/501)."""
        try:
            self._request("GET", url, headers={"Range": "bytes=0-0"})
            return True
        except WebDavError as exc:
            if exc.status_code == 404:
                return False
            if exc.status_code in {200, 206, 416}:
                return True
            raise

    def download(self, url: str | None = None) -> bytes:
        _, body, _ = self._request("GET", url or self._config.remote_url())
        return body

    def upload(self, url: str, payload: bytes, *, content_type: str = "application/json; charset=utf-8") -> None:
        self._ensure_collection(url)
        self._request("PUT", url, data=payload, headers={"Content-Type": content_type})

    def _ensure_collection(self, file_url: str) -> None:
        if not file_url.endswith("/"):
            parent = file_url.rsplit("/", 1)[0] + "/"
        else:
            parent = file_url
        base = self._config.url.rstrip("/") + "/"
        if not parent.startswith(base):
            return
        relative = parent[len(base) :].strip("/")
        if not relative:
            return
        current = base
        for segment in relative.split("/"):
            current = f"{current}{segment}/"
            try:
                self._request("MKCOL", current)
            except WebDavError as exc:
                if exc.status_code in {405, 409, 423}:
                    continue
                raise
