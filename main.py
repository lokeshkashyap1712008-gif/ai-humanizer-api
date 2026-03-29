# ============================================================
# main.py — Production FastAPI Entry Point (FINAL)
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

from middleware.auth import verify_rapidapi
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
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

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

# ── Auth Middleware ───────────────────────────────────────
app.middleware("http")(verify_rapidapi)


# ── Request ID Middleware ─────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Security Headers ──────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    # ✅ FIXED: correct method
    secure_headers.framework.fastapi(response)

    return response


# ── Timeout Middleware ────────────────────────────────────
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout"},
        )


# ── Body Size Limit (Streaming Safe) ──────────────────────
@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
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

    # Response
    return {
        "success": True,
        "humanized_text": humanized,
        "original_word_count": word_count,
        "output_word_count": count_words(humanized),
    }