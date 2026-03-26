# ============================================================
# middleware/auth.py — RapidAPI Authentication Middleware
# ============================================================
# Security measures in this file:
#   ✅ hmac.compare_digest() — constant-time comparison,
#      prevents timing-oracle brute-force of RAPIDAPI_SECRET
#   ✅ Plan is validated against VALID_PLANS whitelist —
#      a spoofed header like "x-rapidapi-subscription: god"
#      is silently downgraded to "free"
#   ✅ user_id capped at 128 chars — prevents Redis key
#      injection via an oversized header value
#   ✅ Health endpoint bypasses auth (unchanged)
#   ✅ Secret validated at startup — not silently at runtime
# ============================================================

import hmac
import os
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from config import VALID_PLANS

load_dotenv()

RAPIDAPI_SECRET = os.getenv("RAPIDAPI_SECRET")
if not RAPIDAPI_SECRET:
    raise RuntimeError("Missing RAPIDAPI_SECRET in environment. Check your .env file.")

# Only printable ASCII allowed in user_id (blocks null-byte / CRLF injection)
_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')


async def verify_rapidapi(request: Request, call_next):
    """
    1. Skip auth for /health
    2. Verify proxy secret (constant-time)
    3. Whitelist-validate plan (prevents privilege escalation via spoofed header)
    4. Sanitize user_id (prevents Redis key injection)
    """

    if request.url.path == "/health":
        return await call_next(request)

    proxy_secret = request.headers.get("x-rapidapi-proxy-secret", "")
    raw_user_id  = request.headers.get("x-rapidapi-user", "")
    raw_plan     = request.headers.get("x-rapidapi-subscription", "free").lower()

    # --- Constant-time secret check ---
    if not proxy_secret or not hmac.compare_digest(proxy_secret, RAPIDAPI_SECRET):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # --- Plan whitelist (prevents privilege escalation) ---
    plan = raw_plan if raw_plan in VALID_PLANS else "free"

    # --- Sanitize user_id (cap length, strip unsafe chars) ---
    if _SAFE_ID_RE.match(raw_user_id):
        user_id = raw_user_id
    else:
        # Fall back to a safe anonymous identifier
        user_id = "anonymous"

    request.state.user_id = user_id
    request.state.plan    = plan

    return await call_next(request)