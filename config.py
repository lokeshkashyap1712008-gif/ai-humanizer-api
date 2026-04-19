# ============================================================
# config.py — Plan Limits + Runtime Controls (PRODUCTION)
# ============================================================

import os
from typing import Dict, Set


# ── Helpers ────────────────────────────────────────────────
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ── Environment ────────────────────────────────────────────
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}

STRICT_EXTERNALS = _env_bool("STRICT_EXTERNALS", IS_PRODUCTION)


# ── Plans (Single Source of Truth) ─────────────────────────
# RapidAPI Subscription Tiers: Words + Requests per month
PLAN_CONFIG: Dict[str, dict] = {
    "basic": {
        "price": 0,
        "monthly_words": 500,
        "monthly_requests": 500,
        "per_request_words": 500,
        "modes": {"standard"},
        "priority": False,
        "bulk": False,
    },
    "pro": {
        "price": 9,
        "monthly_words": 10_000,
        "monthly_requests": 500_000,
        "per_request_words": 2_000,
        "modes": {"standard", "aggressive", "academic", "casual"},
        "priority": False,
        "bulk": False,
    },
    "ultra": {
        "price": 19,
        "monthly_words": 50_000,
        "monthly_requests": 500_000,
        "per_request_words": 5_000,
        "modes": {"standard", "aggressive", "academic", "casual"},
        "priority": True,
        "bulk": False,
    },
    "mega": {
        "price": 49,
        "monthly_words": 250_000,
        "monthly_requests": 500_000,
        "per_request_words": 15_000,
        "modes": {"standard", "aggressive", "academic", "casual"},
        "priority": True,
        "bulk": True,
    },
}


# ── Derived Limits (No Duplication) ────────────────────────
PLAN_LIMITS = {
    plan: {
        "monthly_words": cfg["monthly_words"],
        "monthly_requests": cfg["monthly_requests"],
        "per_request": cfg["per_request_words"],
    }
    for plan, cfg in PLAN_CONFIG.items()
}


PLAN_MODE_ACCESS: Dict[str, Set[str]] = {
    plan: cfg["modes"] for plan, cfg in PLAN_CONFIG.items()
}


VALID_PLANS = frozenset(PLAN_CONFIG.keys())
DEFAULT_PLAN = "basic"


# ── Character Limits (Anti-abuse) ──────────────────────────
# Derived: words * avg 7 chars (slightly stricter than before)
PLAN_CHAR_LIMITS = {
    plan: int(cfg["per_request_words"] * 7)
    for plan, cfg in PLAN_CONFIG.items()
}


# ── Security Limits ────────────────────────────────────────
MAX_WORD_LEN = _env_int("MAX_WORD_LEN", 200)


# ── Rate Limits (per minute) ───────────────────────────────
RATE_LIMITS = {
    "basic": "5/minute",
    "pro": "20/minute",
    "ultra": "60/minute",
    "mega": "120/minute",
}


# ── Feature Flags ──────────────────────────────────────────
ENABLE_PRIORITY_QUEUE = True
ENABLE_BULK_ENDPOINT = True


# ── Validation Helper ──────────────────────────────────────
def validate_plan(plan: str) -> str:
    """
    Strict plan validation — NO silent downgrade.
    """
    if plan not in VALID_PLANS:
        raise ValueError(f"Invalid plan: {plan}")
    return plan
