# ============================================================
# main.py — Production FastAPI Entry Point (FIXED)
# ============================================================

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import Secure
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from middleware.rate_limit import limiter, get_rate_limit
from utils.sanitize import sanitize_text, InjectionDetected
from utils.tokens import count_words, get_month_key, get_month_expiry
from utils.ai_router import generate_humanized_text
from utils.redis_client import get_redis
from config import (
    PLAN_LIMITS,
    PLAN_CHAR_LIMITS,
    MAX_WORD_LEN,
    PLAN_MODE_ACCESS,
    VALID_PLANS,
)

# ── Config ────────────────────────────────────────────────
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", 50 * 1024))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))

# ONE secret — read from RAPIDAPI_PROXY_SECRET env var
# Set this in Render to match the Proxy Secret shown in your RapidAPI dashboard
RAPIDAPI_PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "").strip()

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

if not RAPIDAPI_PROXY_SECRET:
    raise RuntimeError("Missing RAPIDAPI_PROXY_SECRET in environment.")

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── App Init ──────────────────────────────────────────────
app = FastAPI(docs_url=None, redoc_url=None)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

secure_headers = Secure()

# ── NOTE ON MIDDLEWARE ORDER ──────────────────────────────
# FastAPI runs middleware in REVERSE order of registration.
# The LAST middleware added runs FIRST on incoming requests.
# We register: body_limit → timeout → security → request_id → auth
# Execution order: auth → request_id → security → timeout → body_limit
# Auth MUST run first so request.state.plan/user_id are set
# before the route handler is reached.

# ── 5. Body Size Limit (registered first = runs last) ─────
@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    total = 0
    chunks = []

    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "Request too large"},
            )
        chunks.append(chunk)

    body = b"".join(chunks)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    return await call_next(request)


# ── 4. Timeout ────────────────────────────────────────────
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout"},
        )


# ── 3. Security Headers ───────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


# ── 2. Request ID ─────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── 1. Auth (registered last = runs FIRST) ───────────────
# This is the ONLY place we check the proxy secret and set
# request.state.plan and request.state.user_id.
# auth.py's verify_rapidapi is NOT used — it created the
# duplicate-check conflict that caused the 401.
import hashlib
import hmac
import re

_SECRET_BYTES = RAPIDAPI_PROXY_SECRET.encode("utf-8")
_MAX_SECRET_LEN = 512
_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')


def _anonymous_id(request: Request) -> str:
    client_ip = (request.client.host if request.client else "unknown").encode("utf-8")
    ip_hash = hashlib.sha256(client_ip).hexdigest()[:16]
    return f"anon-{ip_hash}"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Always allow health checks (required for RapidAPI probes)
    if request.url.path == "/health":
        return await call_next(request)

    # ── Check required headers ────────────────────────────
    required = ["x-rapidapi-key", "x-rapidapi-user", "x-rapidapi-host", "x-rapidapi-proxy-secret"]
    for header in required:
        if header not in request.headers:
            return JSONResponse(
                status_code=401,
                content={"error": f"Missing header: {header}"},
            )

    # ── Verify proxy secret (constant-time) ───────────────
    raw_secret = request.headers.get("x-rapidapi-proxy-secret", "")
    if len(raw_secret) > _MAX_SECRET_LEN:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    try:
        authorized = hmac.compare_digest(
            raw_secret.encode("utf-8"),
            _SECRET_BYTES,
        )
    except Exception:
        authorized = False

    if not authorized:
        logger.warning(
            "Auth failed — proxy secret mismatch. "
            "Check RAPIDAPI_PROXY_SECRET in Render matches your RapidAPI dashboard."
        )
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # ── Plan whitelist ────────────────────────────────────
    raw_plan = request.headers.get("x-rapidapi-subscription", "free").lower()
    plan = raw_plan if raw_plan in VALID_PLANS else "free"

    # ── Sanitize user_id ──────────────────────────────────
    raw_user_id = request.headers.get("x-rapidapi-user", "")
    user_id = raw_user_id if _SAFE_ID_RE.match(raw_user_id) else _anonymous_id(request)

    request.state.user_id = user_id
    request.state.plan = plan

    logger.info("Auth OK user=%s plan=%s", user_id, plan)

    return await call_next(request)


# ── Rate Limit Handler ────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    plan = getattr(request.state, "plan", "free")
    msgs = {
        "free": "5 requests/minute",
        "basic": "20 requests/minute",
        "pro": "60 requests/minute",
        "ultra": "120 requests/minute",
    }
    return JSONResponse(
        status_code=429,
        content={"error": f"Rate limit exceeded: {msgs.get(plan, '5 requests/minute')}"},
    )


# ── Global Exception Handler ──────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled error request_id=%s",
        getattr(request.state, "request_id", "unknown"),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ── Lua Script (Quota System) ─────────────────────────────
_BUDGET_LUA = """
local key      = KEYS[1]
local limit    = tonumber(ARGV[1])
local add      = tonumber(ARGV[2])
local expiry   = tonumber(ARGV[3])

local current  = tonumber(redis.call('GET', key) or 0)

if current + add > limit then
    return -1
end

local new_total = redis.call('INCRBY', key, add)

local expiry_ok = redis.call('EXPIREAT', key, expiry)
if expiry_ok == 0 then
    return -2
end

return new_total
"""


# ── Request Model ─────────────────────────────────────────
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_BODY_SIZE)
    mode: str = Field(
        default="standard",
        pattern="^(standard|aggressive|academic|casual)$",
    )


# ── Health Route ──────────────────────────────────────────
@app.get("/health")
async def health():
    try:
        redis = get_redis()
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded"},
        )


# ── Main Route ────────────────────────────────────────────
@app.post("/humanize")
@limiter.limit(get_rate_limit)
async def humanize(request: Request, body: HumanizeRequest):

    request_id = getattr(request.state, "request_id", "unknown")

    # Auth middleware guarantees these exist, but guard anyway
    if not hasattr(request.state, "plan") or request.state.plan not in VALID_PLANS:
        raise HTTPException(status_code=401, detail="Invalid subscription plan")

    user_id = request.state.user_id
    plan = request.state.plan

    # Mode access
    if body.mode not in PLAN_MODE_ACCESS[plan]:
        raise HTTPException(status_code=403, detail="Mode not allowed for your plan")

    # Sanitize
    try:
        clean_text = sanitize_text(body.text)
    except InjectionDetected:
        logger.warning("Injection detected request_id=%s", request_id)
        raise HTTPException(status_code=400, detail="Invalid input")

    if not clean_text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Limits
    if len(clean_text) > PLAN_CHAR_LIMITS[plan]:
        raise HTTPException(status_code=400, detail="Character limit exceeded")

    words = clean_text.split()

    if any(len(w) > MAX_WORD_LEN for w in words):
        raise HTTPException(status_code=400, detail="Invalid token detected")

    if len(words) > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(status_code=400, detail="Word limit exceeded")

    word_count = len(words)

    # Redis quota
    now = datetime.now(timezone.utc)
    redis = get_redis()
    key = get_month_key(user_id, now)

    try:
        result = await redis.eval(
            _BUDGET_LUA,
            1,
            key,
            str(PLAN_LIMITS[plan]["monthly"]),
            str(word_count),
            str(get_month_expiry(now)),
        )
        result = int(result)
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")

    if result == -1:
        raise HTTPException(status_code=429, detail="Monthly limit exceeded")

    if result == -2:
        raise HTTPException(status_code=503, detail="Quota system error")

    # AI call
    try:
        humanized = await asyncio.wait_for(
            generate_humanized_text(clean_text, body.mode, plan),
            timeout=15,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="AI timeout")
    except Exception:
        raise HTTPException(status_code=502, detail="AI error")

    return {
        "success": True,
        "humanized_text": humanized,
        "original_word_count": word_count,
        "output_word_count": count_words(humanized),
    }