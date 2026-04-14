from fastapi import APIRouter
from pydantic import BaseModel, Field

from controllers.auth_controller import login_user, signup_user

# v1 router (current)
router = APIRouter(prefix="/v1/auth", tags=["auth"])
# Legacy router (deprecated)
legacy_router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)
    plan: str = Field(default="basic", min_length=4, max_length=16)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)


async def _signup_handler(body: SignupRequest):
    return await signup_user(body.email, body.password, body.plan)


async def _login_handler(body: LoginRequest):
    return await login_user(body.email, body.password)


# v1 routes
@router.post("/signup")
async def signup(body: SignupRequest):
    return await _signup_handler(body)


@router.post("/login")
async def login(body: LoginRequest):
    return await _login_handler(body)


# Legacy routes (mirror v1)
@legacy_router.post("/signup")
async def signup_legacy(body: SignupRequest):
    return await _signup_handler(body)


@legacy_router.post("/login")
async def login_legacy(body: LoginRequest):
    return await _login_handler(body)
