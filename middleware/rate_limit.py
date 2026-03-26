# Rate Limiting
# ✅ FIX #6 — Uses Redis backend (not in-memory) so limits survive restarts and work across workers
# ✅ FIX #10 — Per-plan dynamic rate limits instead of one-size-fits-all

import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("Missing UPSTASH_REDIS_URL in environment. Check your .env file.")


def get_user_identifier(request) -> str:
    """Use RapidAPI user ID if present, otherwise fall back to IP address."""
    return request.headers.get("x-rapidapi-user") or get_remote_address(request)


def get_rate_limit(request) -> str:
    """
    Return a per-plan rate limit string.
    ✅ FIX #10 — Free users are throttled more tightly; paid plans get appropriate headroom.
    """
    plan = getattr(request.state, "plan", "free")
    limits = {
        "free":  "5/minute",
        "basic": "20/minute",
        "pro":   "60/minute",
        "ultra": "120/minute",
    }
    return limits.get(plan, "5/minute")


# ✅ FIX #6 — Redis-backed storage instead of memory://
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=REDIS_URL,
)