# AI Humanizer API

Convert AI-generated text into more natural writing with plan-based monthly quotas.

## Endpoints

### Core (v1)
- `POST /v1/humanize`
- `GET /v1/usage`
- `GET /v1/plan`

### Legacy aliases
- `POST /humanize`
- `GET /usage`
- `GET /plan`

### Health
- `GET /health`

## Authentication (RapidAPI Only)

Protected endpoints (`/v1/humanize`, `/v1/usage`, and legacy aliases) use RapidAPI headers:

- `x-rapidapi-key` (required)
- `x-rapidapi-proxy-secret` (required when `REQUIRE_RAPIDAPI_PROXY_SECRET=true`)
- `x-rapidapi-subscription` (`basic|pro|ultra|mega`, optional, defaults to `basic`)
- `x-rapidapi-user` (optional; if missing, API uses a hashed key-based identifier)

Proxy secret configuration supports both:

- `RAPIDAPI_PROXY_SECRET`
- `RAPIDAPI_SECRET` (fallback alias)

## Humanize Request Example

```http
POST /v1/humanize
x-rapidapi-key: <api-key>
x-rapidapi-proxy-secret: <proxy-secret>
x-rapidapi-subscription: pro
Content-Type: application/json

{
  "text": "Your source text...",
  "mode": "standard"
}
```

## Humanize Response Shape

```json
{
  "success": true,
  "humanized_text": "...",
  "original_word_count": 120,
  "output_word_count": 128,
  "mode": "standard",
  "generation": {
    "provider_used": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "fallback_used": false
  },
  "quota": {
    "words_used": 500,
    "words_limit": 10000,
    "words_remaining": 9500,
    "requests_used": 25,
    "requests_limit": 500000,
    "requests_remaining": 499975
  }
}
```

## Plans

- `basic`: 500 words/month, 500 requests/month, 500 words/request, mode `standard`
- `pro`: 10,000 words/month, 500,000 requests/month, 2,000 words/request, all modes
- `ultra`: 50,000 words/month, 500,000 requests/month, 5,000 words/request, all modes
- `mega`: 250,000 words/month, 500,000 requests/month, 15,000 words/request, all modes

## Important Environment Variables

- `RAPIDAPI_PROXY_SECRET` or `RAPIDAPI_SECRET`
- `REQUIRE_RAPIDAPI_PROXY_SECRET` (`true` by default)
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `MAX_BODY_SIZE`
- `REQUEST_TIMEOUT`
- `ALLOWED_ORIGINS`
