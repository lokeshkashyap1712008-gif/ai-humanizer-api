from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from config import PLAN_LIMITS, PLAN_MODE_ACCESS, VALID_PLANS
from controllers.auth_controller import get_user_by_id, login_user, signup_user
from middleware.jwt_auth import require_authenticated_user

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)
    plan: str = Field(default="free", min_length=4, max_length=16)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)


@router.post("/signup")
async def signup(body: SignupRequest):
    return await signup_user(body.email, body.password, body.plan)


@router.post("/login")
async def login(body: LoginRequest):
    return await login_user(body.email, body.password)


@router.get("/me")
async def me(
    request: Request,
    _user_id: str = Depends(require_authenticated_user),
):
    user_doc = await get_user_by_id(request.state.user_id)
    plan = str(user_doc.get("plan") or request.state.plan or "free").lower()
    if plan not in VALID_PLANS:
        plan = "free"

    return {
        "success": True,
        "user": {
            "userId": user_doc.get("user_id"),
            "email": user_doc.get("email"),
            "plan": plan,
        },
        "rights": {
            "modes": sorted(PLAN_MODE_ACCESS[plan]),
            "monthly_words": PLAN_LIMITS[plan]["monthly"],
            "per_request_words": PLAN_LIMITS[plan]["per_request"],
        },
    }
