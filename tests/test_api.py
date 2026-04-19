from uuid import uuid4

from fastapi.testclient import TestClient

import main
from utils.ai_router import GenerationResult
from utils.redis_client import _InMemoryRedis


client = TestClient(main.app)


def setup_function():
    main.app.state.limiter.reset()
    main.app.state._state["limiter"] = main.limiter
    main.app.dependency_overrides = {}
    main.get_redis.__globals__["_redis"] = _InMemoryRedis()


def _signup_and_token(plan: str = "pro") -> str:
    email = f"test-{uuid4().hex}@example.com"
    response = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "SuperSecurePassword123!",
            "plan": plan,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_plan_endpoint_is_public():
    response = client.get("/v1/plan")

    assert response.status_code == 200
    body = response.json()
    assert "plans" in body
    assert body["plans"]["basic"]["per_request_words"] == 500


def test_auth_round_trip_and_me_endpoint():
    token = _signup_and_token(plan="ultra")

    me_response = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200, me_response.text
    payload = me_response.json()
    assert payload["success"] is True
    assert payload["user"]["plan"] == "ultra"
    assert "academic" in payload["rights"]["modes"]


def test_humanize_endpoint_returns_generation_and_quota(monkeypatch):
    async def fake_generate(text: str, mode: str, plan: str) -> GenerationResult:
        return GenerationResult(
            text=f"{text} Humanized.",
            provider_used="anthropic",
            model="test-model",
            fallback_used=False,
        )

    monkeypatch.setattr(main, "generate_humanized_text", fake_generate)

    token = _signup_and_token(plan="pro")
    response = client.post(
        "/v1/humanize",
        headers={"Authorization": f"Bearer {token}"},
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
