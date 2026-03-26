# RapidAPI Authentication Middleware
# Verifies proxy secret and extracts user + plan
# ✅ FIX #5 — Uses hmac.compare_digest to prevent timing attacks

import hmac
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_SECRET = os.getenv("RAPIDAPI_SECRET")

if not RAPIDAPI_SECRET:
    raise RuntimeError("Missing RAPIDAPI_SECRET in environment. Check your .env file.")


async def verify_rapidapi(request: Request, call_next):
    """
    Middleware to:
    1. Verify x-rapidapi-proxy-secret using constant-time comparison (prevents timing attacks)
    2. Extract user_id and subscription plan
    3. Attach them to request.state
    """

    # Allow health check without auth
    if request.url.path == "/health":
        return await call_next(request)

    # Get headers
    proxy_secret = request.headers.get("x-rapidapi-proxy-secret", "")
    user_id = request.headers.get("x-rapidapi-user")
    plan = request.headers.get("x-rapidapi-subscription", "free")

    # ✅ FIX #5 — Constant-time comparison prevents timing-based secret brute-force
    if not proxy_secret or not hmac.compare_digest(proxy_secret, RAPIDAPI_SECRET):
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized"},
        )

    # Attach user info to request state
    request.state.user_id = user_id or "anonymous"
    request.state.plan = plan.lower()

    return await call_next(request)