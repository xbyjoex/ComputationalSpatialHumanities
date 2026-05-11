"""Base HTTP extractor with retry logic."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import settings

logger = logging.getLogger(__name__)

RETRY_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _make_retry(max_retries: int = settings.max_retries):
    return retry(
        retry=retry_if_exception_type(RETRY_EXCEPTIONS),
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(
            multiplier=settings.backoff_factor, min=2, max=30
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


class HttpExtractor:
    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=settings.request_timeout,
                follow_redirects=True,
                headers={"User-Agent": "Leipzig-Open-Data-ETL/1.0"},
                http2=True,
            )
        return self._client

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    @_make_retry()
    def get_json(self, url: str, params: dict | None = None) -> Any:
        resp = self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @_make_retry()
    def get_text(self, url: str, params: dict | None = None) -> str:
        resp = self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.text

    @_make_retry()
    def get_bytes(self, url: str) -> bytes:
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.content

    def fetch_with_headers(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> httpx.Response:
        """HEAD with conditional headers to check freshness without downloading body."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        try:
            resp = self.client.head(url, headers=headers, follow_redirects=True)
            return resp
        except Exception:
            # HEAD not supported — return a fake 200 to force normal download
            class _FakeResp:
                status_code = 200
                headers: dict = {}
            return _FakeResp()  # type: ignore

    def __enter__(self) -> "HttpExtractor":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
