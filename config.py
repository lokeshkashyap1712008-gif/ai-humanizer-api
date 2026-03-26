# ============================================================
# config.py — Plan Limits + Mode Access Control
# ============================================================
# Matches pricing page exactly:
#   Free:  $0   — 500 words/mo,     standard only,   500/req
#   Basic: $9   — 10,000 words/mo,  all 4 modes,   2,000/req
#   Pro:   $19  — 50,000 words/mo,  all 4 modes,   5,000/req
#   Ultra: $49  — 250,000 words/mo, all 4 modes,  15,000/req
# ============================================================

PLAN_LIMITS = {
    "free":  {"monthly": 500,    "per_request": 500},
    "basic": {"monthly": 10_000, "per_request": 2_000},
    "pro":   {"monthly": 50_000, "per_request": 5_000},
    "ultra": {"monthly": 250_000,"per_request": 15_000},
}

# Per-plan character limits (defence against single-"word" cost amplification).
# Derived from per_request word limit * avg 6 chars/word, rounded generously.
PLAN_CHAR_LIMITS = {
    "free":  3_500,
    "basic": 14_000,
    "pro":   35_000,
    "ultra": 105_000,
}

# Maximum length of any single whitespace-separated token (word).
# Prevents submitting one 20 000-char blob that counts as 1 word
# but generates thousands of AI output tokens.
MAX_WORD_LEN = 200

# Which modes each plan may use
PLAN_MODE_ACCESS = {
    "free":  {"standard"},
    "basic": {"standard", "aggressive", "academic", "casual"},
    "pro":   {"standard", "aggressive", "academic", "casual"},
    "ultra": {"standard", "aggressive", "academic", "casual"},
}

# Valid plans — anything else is downgraded to "free"
VALID_PLANS = frozenset(PLAN_LIMITS.keys())