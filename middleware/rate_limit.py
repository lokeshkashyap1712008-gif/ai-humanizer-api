"""Rate-limit configuration with Redis in production and memory fallback in local dev."""

import logging
import os

import redis as sync_redis
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from config import STRICT_EXTERNALS, APP_ENV

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("UPSTASH_REDIS_URL", "").strip()


if REDIS_URL:
    # Validate Redis before constructing the limiter.
    # This prevents a silent fallback to in-memory in production.
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
            "Rate limiter Redis probe failed - UPSTASH_REDIS_URL may be wrong "
            f"or Redis is unreachable: {exc}"
        ) from exc
    _storage_uri = REDIS_URL
else:
    if STRICT_EXTERNALS:
        raise RuntimeError(
            "Missing UPSTASH_REDIS_URL. Production/strict mode requires Redis "
            f"(APP_ENV={APP_ENV}, STRICT_EXTERNALS={STRICT_EXTERNALS})."
        )
    logger.warning(
        "UPSTASH_REDIS_URL is missing. Using in-memory rate limiting; limits reset on restart."
    )
    _storage_uri = "memory://"


def get_user_identifier(request) -> str:
    """
    Encode plan into the key so slowapi's dynamic limit provider can
    derive per-plan limits from the `key` argument.
    """
    user_id = getattr(request.state, "user_id", None) or get_remote_address(request)
    plan = getattr(request.state, "plan", "free")
    return f"{plan}:{user_id}"


def get_rate_limit(key: str) -> str:
    """Return a per-plan rate limit string from the encoded limiter key."""
    plan = (key.split(":", 1)[0] if ":" in key else "free").lower()
    limits = {
        "free": "5/minute",
        "basic": "20/minute",
        "pro": "60/minute",
        "ultra": "120/minute",
    }
    return limits.get(plan, "5/minute")


limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=_storage_uri,
)
