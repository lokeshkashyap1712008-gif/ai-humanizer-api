"""Async Redis client using Upstash REST API with in-memory fallback."""

import asyncio
import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv
from config import STRICT_EXTERNALS, APP_ENV

load_dotenv()

logger = logging.getLogger(__name__)

_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()


class _InMemoryRedis:
    def __init__(self):
        self._store: dict[str, int] = {}
        self._expiry: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _purge_if_expired(self, key: str, now_ts: int) -> None:
        exp = self._expiry.get(key)
        if exp is not None and now_ts >= exp:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        now_ts = int(time.time())
        async with self._lock:
            self._purge_if_expired(key, now_ts)
            value = self._store.get(key)
            return str(value) if value is not None else None

    async def ping(self) -> str:
        return "PONG"

    async def eval(self, _script: str, _numkeys: int, key: str, limit: str, add: str, expiry: str) -> int:
        monthly_limit = int(limit)
        increment = int(add)
        expiry_ts = int(expiry)
        now_ts = int(time.time())

        async with self._lock:
            self._purge_if_expired(key, now_ts)
            current = int(self._store.get(key, 0))
            if current + increment > monthly_limit:
                return -1
            self._store[key] = current + increment
            self._expiry[key] = expiry_ts
            return current + increment


class _UpstashRedis:
    """Async wrapper around upstash-redis for use in async code."""

    def __init__(self):
        from upstash_redis import Redis
        self._r = Redis(url=_REST_URL, token=_REST_TOKEN)

    async def ping(self) -> str:
        return self._r.ping()

    async def get(self, key: str) -> Optional[str]:
        val = self._r.get(key)
        return str(val) if val is not None else None

    async def eval(self, script: str, numkeys: int, key: str, limit: str, add: str, expiry: str) -> int:
        return self._r.eval(script, numkeys, [key], [limit, add, expiry])


if _REST_URL and _REST_TOKEN:
    _redis = _UpstashRedis()
else:
    if STRICT_EXTERNALS:
        raise RuntimeError(
            "Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN. "
            f"Production/strict mode requires Redis (APP_ENV={APP_ENV})."
        )
    logger.warning("Upstash credentials missing. Using in-memory quota store.")
    _redis = _InMemoryRedis()


def get_redis():
    return _redis