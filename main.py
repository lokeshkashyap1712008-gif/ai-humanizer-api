# FINAL PRODUCTION MAIN.PY

import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import SecureHeaders

# Middleware + utils
from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter
from utils.sanitize import sanitize_text
from utils.tokens import count_words, estimate_tokens
from utils.ai_router import generate_humanized_text
from config import PLAN_LIMITS

# SlowAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# -----------------------------
# App Init (DOCS DISABLED)
# -----------------------------
app = FastAPI(
    docs_url=None,
    redoc_url=None
)

# Attach limiter
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Auth middleware
app.middleware("http")(verify_rapidapi)

# Security headers
secure_headers = SecureHeaders()


# -----------------------------
# SECURITY MIDDLEWARES
# -----------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout"}
        )


@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    body = await request.body()
    if len(body) > 50 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": "Request too large"}
        )
    return await call_next(request)


# -----------------------------
# RATE LIMIT HANDLER
# -----------------------------
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Max 10 requests per minute"}
    )


# -----------------------------
# GLOBAL ERROR HANDLER
# -----------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# -----------------------------
# REQUEST MODEL
# -----------------------------
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mode: str = Field(default="standard", pattern="^(standard|aggressive|academic|casual)$")


# -----------------------------
# ROUTES
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# HUMANIZE ENDPOINT
# -----------------------------
@app.post("/humanize")
@limiter.limit("10/minute")
async def humanize(request: Request, body: HumanizeRequest):

    user_id = request.state.user_id
    plan = request.state.plan

    if not body.text.strip():
        raise HTTPException(status_code=400, detail={"error": "Text is required"})

    # Sanitize
    clean_text = sanitize_text(body.text)

    # Word count
    word_count = count_words(clean_text)

    if plan not in PLAN_LIMITS:
        plan = "free"

    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={"error": "Request exceeds per-request word limit"}
        )

    # AI
    try:
        humanized_text = await generate_humanized_text(
            clean_text,
            body.mode,
            plan
        )
    except Exception as e:
        if str(e) == "timeout":
            raise HTTPException(status_code=408, detail={"error": "AI request timeout"})
        else:
            raise HTTPException(status_code=502, detail={"error": "AI service error. Try again."})

    # Token tracking
    tokens_used = estimate_tokens(clean_text)

    # Headers
    limit = PLAN_LIMITS[plan]["monthly"]
    used = 0
    remaining = limit - used

    response = JSONResponse(
        content={
            "success": True,
            "humanized_text": humanized_text,
            "original_word_count": len(body.text.split()),
            "output_word_count": len(humanized_text.split()),
            "mode": body.mode,
            "tokens_used": tokens_used
        }
    )

    response.headers["X-Words-Used"] = str(used)
    response.headers["X-Words-Limit"] = str(limit)
    response.headers["X-Words-Remaining"] = str(remaining)

    return response