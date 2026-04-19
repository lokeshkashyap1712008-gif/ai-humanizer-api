from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from config import DEFAULT_PLAN, PLAN_LIMITS, PLAN_MODE_ACCESS, VALID_PLANS
from controllers.auth_controller import get_user_by_id, login_user, signup_user
from middleware.jwt_auth import require_authenticated_user

# v1 router (current)
router = APIRouter(prefix="/v1/auth", tags=["auth"])
# Legacy router (deprecated)
legacy_router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)
    plan: str = Field(default=DEFAULT_PLAN, min_length=3, max_length=16)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)


async def _signup_handler(body: SignupRequest):
    return await signup_user(body.email, body.password, body.plan)


async def _login_handler(body: LoginRequest):
    return await login_user(body.email, body.password)


async def _me_handler(request: Request):
    user_doc = await get_user_by_id(request.state.user_id)
    plan = str(user_doc.get("plan") or request.state.plan or DEFAULT_PLAN).lower()
    if plan not in VALID_PLANS:
        plan = DEFAULT_PLAN

    return {
        "success": True,
        "user": {
            "userId": user_doc.get("user_id"),
            "email": user_doc.get("email"),
            "plan": plan,
        },
        "rights": {
            "modes": sorted(PLAN_MODE_ACCESS[plan]),
            "monthly_words": PLAN_LIMITS[plan]["monthly_words"],
            "monthly_requests": PLAN_LIMITS[plan]["monthly_requests"],
            "per_request_words": PLAN_LIMITS[plan]["per_request"],
        },
    }


# v1 routes
@router.post("/signup")
async def signup(body: SignupRequest):
    return await _signup_handler(body)


@router.post("/login")
async def login(body: LoginRequest):
    return await _login_handler(body)


@router.get("/me")
async def me(
    request: Request,
    _user_id: str = Depends(require_authenticated_user),
):
    return await _me_handler(request)


# Legacy routes (mirror v1)
@legacy_router.post("/signup")
async def signup_legacy(body: SignupRequest):
    return await _signup_handler(body)


@legacy_router.post("/login")
async def login_legacy(body: LoginRequest):
    return await _login_handler(body)


@legacy_router.get("/me")
async def me_legacy(
    request: Request,
    _user_id: str = Depends(require_authenticated_user),
):
    return await _me_handler(request)
