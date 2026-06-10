"""Invalidate the backend tile cache after data changes.

Bump-version pattern: the backend includes `tiles:version` in every tile
cache key, so an INCR invalidates all tiles at once without SCAN/DEL storms;
stale generations age out via Redis LRU eviction.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def bump_tiles_version() -> None:
    url = os.getenv("REDIS_URL", "")
    if not url:
        return
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        version = client.incr("tiles:version")
        client.close()
        logger.info("Tile cache invalidated (tiles:version=%s)", version)
    except Exception as exc:
        logger.warning("Tile cache version bump failed: %s", exc)
