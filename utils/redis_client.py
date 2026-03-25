# Redis singleton client (Upstash compatible)

import os
import redis
from dotenv import load_dotenv

load_dotenv()

_redis = None


def get_redis():
    global _redis

    if _redis is None:
        _redis = redis.Redis.from_url(
            os.getenv("UPSTASH_REDIS_URL"),
            socket_timeout=3,
            socket_connect_timeout=3,
            decode_responses=True
        )

    return _redis