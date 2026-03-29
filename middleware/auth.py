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
#   ✅ /health bypasses auth (required for RapidAPI probes)
# ============================================================

import hashlib
import hmac
import logging
import os
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from config import VALID_PLANS

load_dotenv()

logger = logging.getLogger(__name__)

RAPIDAPI_SECRET = (
    os.getenv("RAPIDAPI_PROXY_SECRET")
    or os.getenv("RAPIDAPI_SECRET")
)
if not RAPIDAPI_SECRET:
    raise RuntimeError(
        "Missing RapidAPI proxy secret in environment. "
        "Set RAPIDAPI_PROXY_SECRET (preferred) or RAPIDAPI_SECRET."
    )

# Encode once at startup — avoids per-request allocation
_SECRET_BYTES = RAPIDAPI_SECRET.encode("utf-8")

# Only printable ASCII, 1–128 chars (blocks null-byte / CRLF injection)
_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')

# Cap incoming secret header length before comparison to prevent memory pressure
_MAX_SECRET_LEN = 512


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

    if request.method == "OPTIONS" or request.url.path in {"/", "/health"}:
        logger.info(
            "rapidapi_auth bypass method=%s path=%s",
            request.method,
            request.url.path,
        )
        return await call_next(request)

    raw_secret   = request.headers.get("x-rapidapi-proxy-secret", "")
    raw_user_id  = request.headers.get("x-rapidapi-user", "")
    raw_plan     = request.headers.get("x-rapidapi-subscription", "free").lower()

    logger.info(
        "rapidapi_auth request path=%s method=%s has_proxy_secret=%s secret_len=%s has_key=%s has_host=%s has_user=%s plan=%s",
        request.url.path,
        request.method,
        bool(raw_secret),
        len(raw_secret),
        "x-rapidapi-key" in request.headers,
        "x-rapidapi-host" in request.headers,
        bool(raw_user_id),
        raw_plan,
    )

    # ── Constant-time secret verification ─────────────────
    # Cap length first to avoid hashing a multi-MB attacker-supplied string.
    if len(raw_secret) > _MAX_SECRET_LEN:
        logger.warning(
            "rapidapi_auth reject reason=secret_too_long path=%s len=%s",
            request.url.path,
            len(raw_secret),
        )
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
        logger.warning(
            "rapidapi_auth reject reason=secret_mismatch path=%s secret_len=%s configured_len=%s",
            request.url.path,
            len(raw_secret),
            len(_SECRET_BYTES),
        )
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

    logger.info(
        "rapidapi_auth accepted path=%s user_id=%s plan=%s",
        request.url.path,
        user_id,
        plan,
    )

    return await call_next(request)
