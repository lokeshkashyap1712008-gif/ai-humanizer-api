from fastapi import APIRouter
from pydantic import BaseModel, Field

from controllers.auth_controller import login_user, signup_user

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
