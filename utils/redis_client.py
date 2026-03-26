# ============================================================
# utils/redis_client.py — Async Redis Singleton (Upstash)
# ============================================================
# Security / correctness measures in this file:
#   ✅ UPSTASH_REDIS_URL validated at startup
#   ✅ FIX: Switched from redis.Redis (synchronous) to
#      redis.asyncio.Redis (asynchronous).
#
#      The original synchronous client blocked the FastAPI
#      event loop on every redis.get() and pipe.execute()
#      call inside the async humanize handler. Under moderate
#      concurrency (many simultaneous requests), each Redis
#      round-trip (~1–5 ms) would freeze the entire event
#      loop, preventing other coroutines from making progress
#      and causing cascading 408 Request Timeout errors.
#
#      redis.asyncio.Redis is a drop-in replacement that
#      suspends the coroutine (await) during I/O instead of
#      blocking the thread, keeping the event loop responsive.
#
#      Callers must await all Redis operations:
#        used = int(await redis.get(month_key) or 0)
#        await pipe.execute()
# ============================================================

import os
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

_REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
if not _REDIS_URL:
    raise RuntimeError("Missing UPSTASH_REDIS_URL in environment. Check your .env file.")

# Created once at import — safe across async workers, no lazy-init race condition.
# FIX: redis.asyncio.Redis instead of redis.Redis — non-blocking I/O.
_redis = aioredis.Redis.from_url(
    _REDIS_URL,
    socket_timeout=3,
    socket_connect_timeout=3,
    decode_responses=True,
)


def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client."""
    return _redis