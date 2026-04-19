# ============================================================
# middleware/rate_limit.py — Production Rate Limiting
# ============================================================

import logging
import os

import redis as sync_redis
from dotenv import load_dotenv
from slowapi import Limiter
from config import DEFAULT_PLAN, STRICT_EXTERNALS, APP_ENV, RATE_LIMITS

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "").strip()


# ── Redis Setup ────────────────────────────────────────────
def _init_storage():
    if REDIS_URL:
        try:
            client = sync_redis.Redis.from_url(
                REDIS_URL,
                socket_timeout=3,
                socket_connect_timeout=3,
                decode_responses=True,
            )
            client.ping()
            client.close()

            logger.info("Rate limiter using Redis backend")
            return REDIS_URL

        except Exception as exc:
            if STRICT_EXTERNALS:
                raise RuntimeError(
                    "Redis connection failed in production"
                ) from exc

            logger.warning("Redis unavailable → falling back to memory")
            return "memory://"

    if STRICT_EXTERNALS:
        raise RuntimeError(
            f"Missing UPSTASH_REDIS_URL (APP_ENV={APP_ENV})"
        )

    logger.warning("Using in-memory rate limiting (dev mode)")
    return "memory://"


_storage_uri = _init_storage()


# ── Key Function (CRITICAL) ─────────────────────────────────
def get_user_identifier(request) -> str:
    """
    Build a robust, unique key per user.

    Priority:
    1. RapidAPI key (best)
    2. user_id (fallback)
    3. IP (last resort - only for public endpoints)
    """

    headers = request.headers

    api_key = headers.get("x-rapidapi-key")
    user_id = getattr(request.state, "user_id", None)
    plan = getattr(request.state, "plan", DEFAULT_PLAN)

    if api_key:
        # Use hashed API key to avoid key exposure in Redis
        import hashlib
        identity = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    elif user_id:
        identity = user_id
    elif request.client:
        # Only use IP for public endpoints with no auth
        identity = request.client.host
    else:
        identity = "unknown"

    # Namespaced key (future-proof)
    return f"rl:v1:{plan}:{identity}"


# ── Dynamic Rate Limit ─────────────────────────────────────
def get_rate_limit(key: str) -> str:
    """
    Extract plan from key and return configured rate.
    """

    try:
        # rl:v1:plan:user
        parts = key.split(":")
        plan = parts[2] if len(parts) >= 3 else DEFAULT_PLAN
    except Exception:
        plan = DEFAULT_PLAN

    return RATE_LIMITS.get(plan, RATE_LIMITS[DEFAULT_PLAN])


# ── Limiter Instance ───────────────────────────────────────
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=_storage_uri,
    strategy="fixed-window",  # predictable for billing
)
