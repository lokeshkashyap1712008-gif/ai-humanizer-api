from fastapi import HTTPException, Request, status
from jwt import ExpiredSignatureError, InvalidTokenError

from config import DEFAULT_PLAN, VALID_PLANS
from controllers.auth_controller import get_user_by_id
from utils.jwt_utils import decode_access_token


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "").strip()
    if not auth_header:
        return ""

    if not auth_header.lower().startswith("bearer "):
        return ""

    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is missing",
        )

    return token


async def require_authenticated_user(request: Request) -> str:
    token = _extract_bearer_token(request)

    if token:
        try:
            payload = decode_access_token(token)
        except RuntimeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT is not configured",
            )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        user_id = str(payload.get("userId") or "").strip()
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user_doc = await get_user_by_id(user_id)

        plan = str(user_doc.get("plan") or DEFAULT_PLAN).lower()
        if plan not in VALID_PLANS:
            plan = DEFAULT_PLAN

        request.state.user_id = user_id
        request.state.plan = plan

        return user_id

    if hasattr(request.state, "user_id") and hasattr(request.state, "plan"):
        return request.state.user_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization required",
    )
