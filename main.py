# ============================================================
# main.py — Production FastAPI Entry Point
# ============================================================
# Security layers present in this file:
#   ✅ Docs disabled (no /docs or /redoc in production)
#   ✅ Security headers via `secure` library
#   ✅ 30 s request timeout (async, non-blocking)
#   ✅ 50 KB body size hard limit (checked before parsing)
#   ✅ RapidAPI proxy-secret auth (constant-time comparison)
#   ✅ Per-plan dynamic rate limiting (Redis-backed)
#   ✅ Plan mode-access enforcement (Free = standard only)
#   ✅ Per-request word-count cap (per plan)
#   ✅ Monthly word budget tracked atomically in Redis
#   ✅ All AI errors returned as opaque 502 — no internals
#   ✅ Global exception handler — no stack traces to clients
#   ✅ X-Content-Type-Options / HSTS etc. via SecureHeaders
# ============================================================

import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import SecureHeaders
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter, get_rate_limit
from utils.sanitize import sanitize_text
from utils.tokens import count_words, estimate_tokens, get_month_key, get_month_expiry
from utils.ai_router import generate_humanized_text
from utils.redis_client import get_redis
from config import PLAN_LIMITS, PLAN_MODE_ACCESS, VALID_PLANS

# ── App init ────────────────────────────────────────────────
app = FastAPI(docs_url=None, redoc_url=None)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.middleware("http")(verify_rapidapi)

secure_headers = SecureHeaders()


# ── Security headers ────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


# ── Request timeout ─────────────────────────────────────────
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse(status_code=408, content={"error": "Request timeout"})


# ── Body size limit ─────────────────────────────────────────
@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 50 * 1024:
        return JSONResponse(status_code=413, content={"error": "Request too large"})
    body = await request.body()          # Starlette caches — safe for downstream
    if len(body) > 50 * 1024:
        return JSONResponse(status_code=413, content={"error": "Request too large"})
    return await call_next(request)


# ── Rate-limit exceeded handler ──────────────────────────────
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    plan = getattr(request.state, "plan", "free")
    msgs = {
        "free":  "5 requests/minute (Free plan)",
        "basic": "20 requests/minute (Basic plan)",
        "pro":   "60 requests/minute (Pro plan)",
        "ultra": "120 requests/minute (Ultra plan)",
    }
    return JSONResponse(
        status_code=429,
        content={"error": f"Rate limit exceeded: {msgs.get(plan, '5 requests/minute')}"},
    )


# ── Global exception handler ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Never leak internal details (stack trace, key names, model names)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── Request model ────────────────────────────────────────────
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    mode: str = Field(
        default="standard",
        pattern="^(standard|aggressive|academic|casual)$",
    )


# ── Routes ───────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/humanize")
@limiter.limit(get_rate_limit)
async def humanize(request: Request, body: HumanizeRequest):

    user_id = request.state.user_id
    plan    = request.state.plan if request.state.plan in VALID_PLANS else "free"

    # ── 1. Mode access enforcement (Free = standard only) ──
    allowed_modes = PLAN_MODE_ACCESS[plan]
    if body.mode not in allowed_modes:
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"Mode '{body.mode}' is not available on the {plan} plan. "
                         f"Upgrade to Basic or above to unlock all modes."
            },
        )

    # ── 2. Sanitize input ──────────────────────────────────
    clean_text = sanitize_text(body.text)

    if not clean_text:
        raise HTTPException(status_code=400, detail={"error": "Text is empty after sanitization"})

    # ── 3. Per-request word cap ────────────────────────────
    word_count = count_words(clean_text)

    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Text exceeds the {PLAN_LIMITS[plan]['per_request']}-word "
                    f"limit for your plan"
                )
            },
        )

    # ── 4. Monthly budget check (Redis) ───────────────────
    redis = get_redis()
    month_key = get_month_key(user_id)

    try:
        used = int(redis.get(month_key) or 0)
    except Exception:
        used = 0   # Fail open — don't block user on Redis read error

    monthly_limit = PLAN_LIMITS[plan]["monthly"]

    if used + word_count > monthly_limit:
        remaining = max(0, monthly_limit - used)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Monthly word limit exceeded",
                "words_used": used,
                "words_limit": monthly_limit,
                "words_remaining": remaining,
            },
        )

    # ── 5. AI call ─────────────────────────────────────────
    try:
        humanized_text = await generate_humanized_text(clean_text, body.mode, plan)
    except Exception as e:
        if str(e) == "timeout":
            raise HTTPException(status_code=408, detail={"error": "AI request timeout"})
        raise HTTPException(status_code=502, detail={"error": "AI service error. Try again."})

    # ── 6. Update monthly usage in Redis (atomic pipeline) ─
    try:
        pipe = redis.pipeline()
        pipe.incrby(month_key, word_count)
        pipe.expireat(month_key, get_month_expiry())
        pipe.execute()
        used_after = used + word_count
    except Exception:
        used_after = used   # Don't crash the response on write failure

    remaining_after = max(0, monthly_limit - used_after)
    tokens_used     = estimate_tokens(clean_text)

    response = JSONResponse(
        content={
            "success": True,
            "humanized_text": humanized_text,
            "original_word_count": len(body.text.split()),
            "output_word_count": len(humanized_text.split()),
            "mode": body.mode,
            "tokens_used": tokens_used,
        }
    )

    response.headers["X-Words-Used"]      = str(used_after)
    response.headers["X-Words-Limit"]     = str(monthly_limit)
    response.headers["X-Words-Remaining"] = str(remaining_after)

    return response