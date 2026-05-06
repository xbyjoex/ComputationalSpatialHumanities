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


async def init_redis() -> None:
    global _redis
    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
    except Exception as exc:
        logger.warning("Redis unavailable, running without cache: %s", exc)
        _redis = None


async def close_redis() -> None:
    if _redis:
        await _redis.aclose()


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
