"""Simple Redis-backed response cache decorator."""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable

import redis.asyncio as aioredis
from fastapi.responses import ORJSONResponse

from .config import settings

logger = logging.getLogger(__name__)
_redis: aioredis.Redis | None = None
_redis_bin: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis, _redis_bin
    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        # Separate binary-safe client for MVT tiles (protobuf bodies)
        _redis_bin = aioredis.from_url(settings.redis_url, decode_responses=False)
        await _redis_bin.ping()
    except Exception as exc:
        logger.warning("Redis unavailable, running without cache: %s", exc)
        _redis = None
        _redis_bin = None


async def close_redis() -> None:
    if _redis:
        await _redis.aclose()
    if _redis_bin:
        await _redis_bin.aclose()


async def tiles_version() -> str:
    """Tile cache generation — bumped by the ETL after nightly mart refresh.

    Stale generations are evicted by Redis LRU rather than deleted.
    """
    if _redis is None:
        return "0"
    try:
        return str(await _redis.get("tiles:version") or "0")
    except Exception:
        return "0"


async def cache_get_bytes(key: str) -> bytes | None:
    if _redis_bin is None:
        return None
    try:
        return await _redis_bin.get(key)
    except Exception:
        return None


async def cache_set_bytes(key: str, value: bytes, ttl: int) -> None:
    if _redis_bin is None:
        return
    try:
        await _redis_bin.setex(key, ttl, value)
    except Exception:
        pass


def cached(ttl: int = 60):
    """
    Decorator for async FastAPI route handlers that caches ORJSONResponse bodies.
    Cache key = function name + stringified kwargs (excluding _user).
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _redis is None:
                return await fn(*args, **kwargs)

            # Build cache key from function + non-user params
            key_data = {k: str(v) for k, v in kwargs.items() if k != "_user"}
            raw_key = f"cache:{fn.__name__}:{json.dumps(key_data, sort_keys=True)}"
            cache_key = hashlib.md5(raw_key.encode()).hexdigest()

            try:
                cached_val = await _redis.get(cache_key)
                if cached_val:
                    return ORJSONResponse(json.loads(cached_val))
            except Exception:
                pass

            result = await fn(*args, **kwargs)

            try:
                if isinstance(result, ORJSONResponse):
                    await _redis.setex(cache_key, ttl, result.body.decode())
            except Exception:
                pass

            return result

        return wrapper

    return decorator
