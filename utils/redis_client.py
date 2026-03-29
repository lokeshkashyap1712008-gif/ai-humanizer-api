# ============================================================
# utils/redis_client.py — Async Redis Client (HARDENED)
# ============================================================

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

REQUEST_TIMEOUT = 5
MAX_RETRIES = 2


# ── In-Memory Fallback ─────────────────────────────────────
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
            val = self._store.get(key)
            return str(val) if val is not None else None

    async def ping(self) -> str:
        return "PONG"

    async def eval(self, _script: str, _numkeys: int, key: str, limit: str, add: str, expiry: str) -> int:
        monthly_limit = int(limit)
        increment = int(add)
        expiry_ts = int(expiry)
        now_ts = int(time.time())

        if increment < 0 or monthly_limit < 0:
            raise ValueError("Invalid quota values")

        async with self._lock:
            self._purge_if_expired(key, now_ts)

            current = int(self._store.get(key, 0))

            if current + increment > monthly_limit:
                return -1

            self._store[key] = current + increment
            self._expiry[key] = expiry_ts

            return current + increment


# ── Upstash Client ─────────────────────────────────────────
class _UpstashRedis:
    def __init__(self):
        from upstash_redis import Redis
        self._r = Redis(url=_REST_URL, token=_REST_TOKEN)

    async def _safe_call(self, func, *args):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(func, *args),
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                if attempt == MAX_RETRIES:
                    logger.error("Redis call failed after retries: %s", e)
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

    async def ping(self) -> str:
        return await self._safe_call(self._r.ping)

    async def get(self, key: str) -> Optional[str]:
        val = await self._safe_call(self._r.get, key)
        return str(val) if val is not None else None

    async def eval(self, script: str, numkeys: int, key: str, limit: str, add: str, expiry: str) -> int:
        _ = numkeys
        result = await self._safe_call(
            self._r.eval,
            script,
            [key],
            [limit, add, expiry],
        )
        return int(result)


# ── Client Selection ───────────────────────────────────────
def _init_client():
    if _REST_URL and _REST_TOKEN:
        try:
            client = _UpstashRedis()
            logger.info("Using Upstash Redis (REST)")
            return client
        except Exception as e:
            if STRICT_EXTERNALS:
                raise RuntimeError("Failed to initialize Redis client") from e

            logger.warning("Redis init failed → falling back to memory: %s", e)

    if STRICT_EXTERNALS:
        raise RuntimeError(
            f"Missing Redis credentials (APP_ENV={APP_ENV})"
        )

    logger.warning("Using in-memory Redis fallback")
    return _InMemoryRedis()


_redis = _init_client()


# ── Public Getter ──────────────────────────────────────────
def get_redis():
    return _redis
