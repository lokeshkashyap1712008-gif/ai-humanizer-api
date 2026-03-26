# Redis singleton client (Upstash compatible)
# ✅ FIX #13 — Initialized at module import time (thread-safe, no race condition)
# ✅ Validates UPSTASH_REDIS_URL at startup

import os
import redis
from dotenv import load_dotenv

load_dotenv()

_REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
if not _REDIS_URL:
    raise RuntimeError("Missing UPSTASH_REDIS_URL in environment. Check your .env file.")

# ✅ Created once at import — safe across async workers, no lazy-init race condition
_redis = redis.Redis.from_url(
    _REDIS_URL,
    socket_timeout=3,
    socket_connect_timeout=3,
    decode_responses=True,
)


def get_redis() -> redis.Redis:
    """Return the shared Redis client."""
    return _redis