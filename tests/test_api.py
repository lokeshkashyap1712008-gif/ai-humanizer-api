import os
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("RAPIDAPI_PROXY_SECRET", "test-proxy-secret")
os.environ.setdefault("REQUIRE_RAPIDAPI_PROXY_SECRET", "true")

import main
from middleware import auth as auth_middleware
from utils.ai_router import GenerationResult
from utils.redis_client import _InMemoryRedis


client = TestClient(main.app)


def setup_function():
    main.app.state.limiter.reset()
    main.app.state._state["limiter"] = main.limiter
    main.app.dependency_overrides = {}
    main.get_redis.__globals__["_redis"] = _InMemoryRedis()
    auth_middleware._EXPECTED_PROXY_SECRET = "test-proxy-secret"
    auth_middleware._REQUIRE_PROXY_SECRET = True


def _rapidapi_headers(
    plan: str = "pro",
    user_id: str | None = None,
    include_api_key: bool = True,
) -> dict[str, str]:
    if user_id is None:
        user_id = f"user-{uuid4().hex[:10]}"

    headers = {
        "x-rapidapi-proxy-secret": "test-proxy-secret",
        "x-rapidapi-subscription": plan,
        "x-rapidapi-user": user_id,
    }
    if include_api_key:
        headers["x-rapidapi-key"] = "test-api-key"
    return headers


def test_plan_endpoint_is_public():
    response = client.get("/v1/plan")

    assert response.status_code == 200
    body = response.json()
    assert "plans" in body
    assert body["plans"]["basic"]["per_request_words"] == 500


def test_humanize_requires_proxy_secret_header():
    headers = _rapidapi_headers()
    headers.pop("x-rapidapi-proxy-secret")

    response = client.post(
        "/v1/humanize",
        headers=headers,
        json={
            "text": "This should fail without proxy secret.",
            "mode": "standard",
        },
    )

    assert response.status_code == 401


def test_humanize_endpoint_returns_generation_and_quota(monkeypatch):
    async def fake_generate(text: str, mode: str, plan: str) -> GenerationResult:
        return GenerationResult(
            text=f"{text} Humanized.",
            provider_used="anthropic",
            model="test-model",
            fallback_used=False,
        )

    monkeypatch.setattr(main, "generate_humanized_text", fake_generate)

    response = client.post(
        "/v1/humanize",
        headers=_rapidapi_headers(plan="pro", user_id="user-pro-1"),
        json={
            "text": "This is a source paragraph that should stay stable.",
            "mode": "academic",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["generation"]["provider_used"] == "anthropic"
    assert payload["quota"]["words_used"] >= payload["original_word_count"]
    assert "X-Ratelimit-Limit" in response.headers


def test_humanize_allows_proxy_secret_without_api_key(monkeypatch):
    async def fake_generate(text: str, mode: str, plan: str) -> GenerationResult:
        return GenerationResult(
            text=f"{text} Humanized.",
            provider_used="anthropic",
            model="test-model",
            fallback_used=False,
        )

    monkeypatch.setattr(main, "generate_humanized_text", fake_generate)

    response = client.post(
        "/v1/humanize",
        headers=_rapidapi_headers(
            plan="basic",
            user_id="user-basic-no-key",
            include_api_key=False,
        ),
        json={
            "text": "Basic plan text sample.",
            "mode": "standard",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode"] == "standard"


def test_usage_endpoint_returns_current_quota(monkeypatch):
    async def fake_generate(text: str, mode: str, plan: str) -> GenerationResult:
        return GenerationResult(
            text=f"{text} rewritten",
            provider_used="fallback",
            model="test-model",
            fallback_used=True,
        )

    monkeypatch.setattr(main, "generate_humanized_text", fake_generate)

    headers = _rapidapi_headers(plan="basic", user_id="usage-user-1")
    seed_response = client.post(
        "/v1/humanize",
        headers=headers,
        json={"text": "Quick sample input for usage meter.", "mode": "standard"},
    )
    assert seed_response.status_code == 200, seed_response.text

    usage_response = client.get("/v1/usage", headers=headers)
    assert usage_response.status_code == 200, usage_response.text

    payload = usage_response.json()
    assert payload["plan"] == "basic"
    assert payload["quotas"]["words"]["used"] > 0
    assert payload["quotas"]["requests"]["used"] > 0
