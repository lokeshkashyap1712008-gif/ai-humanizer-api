# ============================================================
# middleware/auth.py — RapidAPI Authentication Middleware
# ============================================================
# Security measures in this file:
#   ✅ hmac.compare_digest() — constant-time comparison,
#      prevents timing-oracle brute-force of RAPIDAPI_SECRET
#   ✅ Explicit bytes encoding before compare_digest —
#      FIX: previously compared raw str values; a type
#      mismatch (str vs bytes) raises TypeError instead of
#      returning False, which leaks as a 500. Both sides are
#      now .encode("utf-8") before comparison.
#   ✅ Proxy-secret length capped before comparison —
#      prevents memory pressure from oversized header values
#   ✅ Plan validated against VALID_PLANS whitelist —
#      spoofed header "x-rapidapi-subscription: god"
#      is silently downgraded to "free"
#   ✅ user_id validated via printable-ASCII regex, capped
#      at 128 chars — prevents Redis key injection and
#      CRLF injection via oversized header values
#   ✅ Anonymous fallback uses per-IP hash — prevents budget
#      collision DoS where one user exhausts the shared
#      "anonymous" quota for all unauthenticated callers
#   ✅ Secret validated at startup — mis-configured deploys
#      fail immediately rather than silently at runtime
#   ✅ /health and / bypass auth (required for Render + RapidAPI probes)
# ============================================================

import hashlib
import hmac
import os
import re
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from config import VALID_PLANS

load_dotenv()

logger = logging.getLogger(__name__)

RAPIDAPI_SECRET = os.getenv("RAPIDAPI_SECRET")
if not RAPIDAPI_SECRET:
    raise RuntimeError("Missing RAPIDAPI_SECRET in environment. Check your .env file.")

# Encode once at startup — avoids per-request allocation
_SECRET_BYTES = RAPIDAPI_SECRET.encode("utf-8")

# Only printable ASCII, 1–128 chars (blocks null-byte / CRLF injection)
_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')

# Cap incoming secret header length before comparison to prevent memory pressure
_MAX_SECRET_LEN = 512

# Paths that bypass auth entirely (health probes from Render and RapidAPI)
_BYPASS_PATHS = {"/health", "/"}


def _anonymous_id(request: Request) -> str:
    """
    Generate a per-IP anonymous ID instead of a shared literal.

    Each IP gets its own Redis quota key so one caller cannot exhaust
    the budget for all other anonymous callers. Raw IP is hashed so
    it is never stored in Redis in plaintext.
    """
    client_ip = (request.client.host if request.client else "unknown").encode("utf-8")
    ip_hash = hashlib.sha256(client_ip).hexdigest()[:16]
    return f"anon-{ip_hash}"


async def verify_rapidapi(request: Request, call_next):
    """
    1. Skip auth for /health (required by RapidAPI health probes)
    2. Verify proxy secret — constant-time, type-safe bytes comparison
    3. Whitelist-validate plan — prevents privilege escalation
    4. Sanitize user_id — prevents Redis key injection
    """

    if request.url.path in _BYPASS_PATHS:
        return await call_next(request)

    raw_secret   = request.headers.get("x-rapidapi-proxy-secret", "")
    raw_user_id  = request.headers.get("x-rapidapi-user", "")
    raw_plan     = request.headers.get("x-rapidapi-subscription", "free").lower()

    # ── DEBUG logging (remove after confirming fix) ────────
    logger.info("DEBUG raw_secret repr: %r", raw_secret)
    logger.info("DEBUG expected secret repr: %r", RAPIDAPI_SECRET)
    logger.info("DEBUG lengths — received: %d  expected: %d", len(raw_secret), len(RAPIDAPI_SECRET))
    # ───────────────────────────────────────────────────────

    # ── Constant-time secret verification ─────────────────
    # Cap length first to avoid hashing a multi-MB attacker-supplied string.
    if len(raw_secret) > _MAX_SECRET_LEN:
        logger.info("DEBUG 401: secret too long")
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    try:
        # FIX: encode both sides to bytes — str/bytes type mismatch raises
        # TypeError which would surface as 500 instead of 401.
        authorized = hmac.compare_digest(
            raw_secret.encode("utf-8"),
            _SECRET_BYTES,
        )
    except Exception:
        authorized = False

    if not authorized:
        logger.info("DEBUG 401: secret mismatch")
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # ── Plan whitelist ─────────────────────────────────────
    plan = raw_plan if raw_plan in VALID_PLANS else "free"

    # ── Sanitize user_id ───────────────────────────────────
    if _SAFE_ID_RE.match(raw_user_id):
        user_id = raw_user_id
    else:
        user_id = _anonymous_id(request)

    request.state.user_id = user_id
    request.state.plan    = plan

    return await call_next(request)