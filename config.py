# ============================================================
# config.py — Plan Limits + Mode Access Control
# NEW: mode_access enforces that Free users can only use
#      "standard" mode — matches the pricing page exactly.
# ============================================================

PLAN_LIMITS = {
    "free":  {"monthly": 500,    "per_request": 500},
    "basic": {"monthly": 10000,  "per_request": 2000},
    "pro":   {"monthly": 50000,  "per_request": 5000},
    "ultra": {"monthly": 250000, "per_request": 15000},
}

# Which modes each plan may use (matches pricing screenshot)
PLAN_MODE_ACCESS = {
    "free":  {"standard"},
    "basic": {"standard", "aggressive", "academic", "casual"},
    "pro":   {"standard", "aggressive", "academic", "casual"},
    "ultra": {"standard", "aggressive", "academic", "casual"},
}

# Valid plans — anything else is downgraded to "free"
VALID_PLANS = frozenset(PLAN_LIMITS.keys())