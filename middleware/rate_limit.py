from slowapi import Limiter
from slowapi.util import get_remote_address

def get_user_identifier(request):
    return request.headers.get("x-rapidapi-user") or get_remote_address(request)

limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri="memory://"
)