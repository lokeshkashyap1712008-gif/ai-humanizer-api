# ============================================================
# utils/tokens.py — Word counting + monthly key helpers
# ============================================================
# Changes from original:
#   ✅ FIX: get_month_key() and get_month_expiry() now accept
#      an optional `now` datetime parameter. Callers snapshot
#      UTC time ONCE and pass it to both functions, eliminating
#      the month-rollover race where the key and the expiry
#      could be computed from different datetime.now() calls
#      that straddle a month boundary.
#   ✅ estimate_tokens() retained but clearly documented as
#      informational only — not used for quota enforcement.
# ============================================================

from datetime import datetime, timezone
from typing import Optional


def count_words(text: str) -> int:
    """Return the number of whitespace-separated words in text."""
    return len(text.split())


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: words * 1.3 (typical English tokenization).
    Informational only — not used for quota enforcement.
    Retained for future cost-estimation or analytics features.
    """
    return int(len(text.split()) * 1.3)


def get_month_key(user_id: str, now: Optional[datetime] = None) -> str:
    """
    Redis key scoped to the current UTC month for a given user.

    Pass a pre-captured `now` to ensure the key and the expiry
    (get_month_expiry) are computed from the same instant.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return f"words:{user_id}:{now.year}-{now.month:02d}"


def get_month_expiry(now: Optional[datetime] = None) -> int:
    """
    Unix timestamp of the start of next month (Redis key TTL target).

    Pass the same `now` used for get_month_key() to guarantee
    both functions agree on which month they're computing for.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int(next_month.timestamp())