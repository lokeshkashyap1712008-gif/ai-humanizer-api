"""Async Redis client with a local in-memory fallback for development."""

import asyncio
import logging
import os
import time
from typing import Optional

import redis.asyncio as aioredis
from dotenv import load_dotenv
from config import STRICT_EXTERNALS, APP_ENV

load_dotenv()

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "").strip()


class _InMemoryRedis:
    """
    Minimal async Redis-like client used when UPSTASH_REDIS_URL is not configured.

    It implements only the methods used by main.py:
    - eval(...): budget check + increment semantics
    - get(key): fetch current value
    """

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

    async def eval(self, _script: str, _numkeys: int, key: str, limit: str, add: str, expiry: str) -> int:
        # Keep behavior consistent with the Lua script in main.py:
        # -1 => over limit
        # -2 => expiry could not be set (not expected here)
        monthly_limit = int(limit)
        increment = int(add)
        expiry_ts = int(expiry)
        now_ts = int(time.time())

        async with self._lock:
            self._purge_if_expired(key, now_ts)
            current = int(self._store.get(key, 0))

            if current + increment > monthly_limit:
                return -1

            new_total = current + increment
            self._store[key] = new_total
            self._expiry[key] = expiry_ts
            return new_total


if _REDIS_URL:
    _redis = aioredis.Redis.from_url(
        _REDIS_URL,
        socket_timeout=3,
        socket_connect_timeout=3,
        decode_responses=True,
    )
else:
    if STRICT_EXTERNALS:
        raise RuntimeError(
            "Missing UPSTASH_REDIS_URL. Production/strict mode requires Redis "
            f"(APP_ENV={APP_ENV}, STRICT_EXTERNALS={STRICT_EXTERNALS})."
        )
    logger.warning(
        "UPSTASH_REDIS_URL is missing. Using in-memory quota store; data will reset on restart."
    )
    _redis = _InMemoryRedis()


def get_redis():
    """Return the shared async Redis-compatible client."""
    return _redis
