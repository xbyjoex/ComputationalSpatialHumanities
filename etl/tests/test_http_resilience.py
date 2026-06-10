"""Regression guard for the opendata.leipzig.de connection-reset failures.

"[Errno 104] Connection reset by peer" surfaces as httpx.ReadError, which the
original retry set (TimeoutException, ConnectError, RemoteProtocolError) did NOT
cover — so the whole election-CSV family failed without a single retry. The fix
retries on the httpx.TransportError base class instead.
"""

from __future__ import annotations

import httpx

from src.extractors.base import RETRY_EXCEPTIONS


def test_read_error_is_retryable():
    # The exact failure mode: reset while reading the response body.
    assert issubclass(httpx.ReadError, RETRY_EXCEPTIONS)


def test_transient_transport_errors_are_retryable():
    for exc in (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.RemoteProtocolError,
        httpx.PoolTimeout,
    ):
        assert issubclass(exc, RETRY_EXCEPTIONS), exc.__name__
