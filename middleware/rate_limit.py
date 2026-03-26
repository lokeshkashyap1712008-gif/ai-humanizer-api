# ============================================================
# middleware/rate_limit.py
# ============================================================
# Security measures in this file:
#   ✅ Redis backend (not in-memory) — limits survive restarts
#      and work correctly across multiple workers
#   ✅ Per-plan dynamic rate limits instead of one-size-fits-all
#   ✅ Rate limiter key uses request.state.user_id (sanitized
#      by auth middleware) not the raw header
#   ✅ FIX: Startup Redis connectivity probe — slowapi silently
#      falls back to an in-memory store if the Redis URI is
#      unreachable at construction time. In-memory storage means
#      rate limits are per-process rather than cluster-wide,
#      allowing each worker to grant the full quota independently.
#      An attacker running N concurrent connections defeats the
#      limit by N×. We ping Redis at module import and raise
#      RuntimeError if it is unreachable so the deploy fails
#      fast rather than running with a broken limiter silently.
#      Note: this is a synchronous probe using redis-py because
#      the module is imported at startup (before the event loop
#      starts). The asyncio client is used at request time.
# ============================================================

import os
import redis as sync_redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("Missing UPSTASH_REDIS_URL in environment. Check your .env file.")

# ── FIX: Validate Redis is reachable before constructing the limiter ──
# slowapi swallows connection errors and falls back to in-memory — this
# probe ensures a mis-configured or offline Redis causes a hard startup
# failure instead of a silent degradation to per-process rate limiting.
try:
    _probe = sync_redis.Redis.from_url(
        REDIS_URL,
        socket_timeout=3,
        socket_connect_timeout=3,
        decode_responses=True,
    )
    _probe.ping()
    _probe.close()
except Exception as exc:
    raise RuntimeError(
        f"Rate limiter Redis probe failed — UPSTASH_REDIS_URL may be wrong "
        f"or Redis is unreachable: {exc}"
    ) from exc


def get_user_identifier(request) -> str:
    """
    Use the sanitized RapidAPI user ID from request.state if present,
    otherwise fall back to IP address.
    """
    return getattr(request.state, "user_id", None) or get_remote_address(request)


def get_rate_limit(request) -> str:
    """Return a per-plan rate limit string."""
    plan = getattr(request.state, "plan", "free")
    limits = {
        "free":  "5/minute",
        "basic": "20/minute",
        "pro":   "60/minute",
        "ultra": "120/minute",
    }
    return limits.get(plan, "5/minute")


limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=REDIS_URL,
)