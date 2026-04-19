import argparse
import hashlib
import json
import os
import sys
from typing import Any

import redis


EMAIL_KEY_PREFIX = "auth:user:email:"
USER_KEY_PREFIX = "auth:user:id:"


def _redis_client() -> redis.Redis:
    redis_url = os.getenv("UPSTASH_REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("UPSTASH_REDIS_URL is required for user inspection")

    return redis.Redis.from_url(redis_url, decode_responses=True)


def _email_key(email: str) -> str:
    normalized = email.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{EMAIL_KEY_PREFIX}{digest}"


def _user_key(user_id: str) -> str:
    return f"{USER_KEY_PREFIX}{user_id.strip()}"


def _load_user(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return json.loads(raw)


def lookup_by_email(client: redis.Redis, email: str) -> int:
    user_id = client.get(_email_key(email))
    if not user_id:
        print("No user found for that email.")
        return 1

    raw_doc = client.get(_user_key(user_id))
    user = _load_user(raw_doc)
    if not user:
        print(f"User id {user_id} exists in email index but has no user document.")
        return 1

    print(json.dumps(user, indent=2, sort_keys=True))
    return 0


def lookup_by_id(client: redis.Redis, user_id: str) -> int:
    raw_doc = client.get(_user_key(user_id))
    user = _load_user(raw_doc)
    if not user:
        print("No user found for that user id.")
        return 1

    print(json.dumps(user, indent=2, sort_keys=True))
    return 0


def list_users(client: redis.Redis, limit: int) -> int:
    count = 0
    cursor = 0

    while True:
        cursor, keys = client.scan(cursor=cursor, match=f"{USER_KEY_PREFIX}*", count=min(limit, 100))
        for key in keys:
            raw_doc = client.get(key)
            user = _load_user(raw_doc)
            if not user:
                continue
            print(json.dumps(user, sort_keys=True))
            count += 1
            if count >= limit:
                return 0

        if cursor == 0:
            break

    if count == 0:
        print("No users found.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect AI Humanizer users in Redis.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    email_parser = subparsers.add_parser("by-email", help="Look up a user by email")
    email_parser.add_argument("email")

    id_parser = subparsers.add_parser("by-id", help="Look up a user by user id")
    id_parser.add_argument("user_id")

    list_parser = subparsers.add_parser("list", help="List user records")
    list_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    try:
        client = _redis_client()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "by-email":
        return lookup_by_email(client, args.email)
    if args.command == "by-id":
        return lookup_by_id(client, args.user_id)
    if args.command == "list":
        return list_users(client, max(args.limit, 1))

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
