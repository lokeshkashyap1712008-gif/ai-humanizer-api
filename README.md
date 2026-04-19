# AI Humanizer API

Convert AI-generated text into more natural writing with plan-based word and request quotas.

## API Endpoints

### Core (v1)
- `POST /v1/humanize`
- `GET /v1/usage`
- `GET /v1/plan`

### Legacy aliases (still supported)
- `POST /humanize`
- `GET /usage`
- `GET /plan`

### Auth
- `POST /v1/auth/signup`
- `POST /v1/auth/login`
- `GET /v1/auth/me`
- `POST /auth/signup` (legacy)
- `POST /auth/login` (legacy)
- `GET /auth/me` (legacy)

### Health
- `GET /health`

## Authentication

`/humanize` and `/v1/humanize` accept two auth modes:

1. RapidAPI headers
- `x-rapidapi-key` (required)
- `x-rapidapi-host` (recommended)
- `x-rapidapi-subscription` (`basic|pro|ultra|mega`)
- optional `x-rapidapi-user`
- optional `x-rapidapi-proxy-secret` (required only if `REQUIRE_RAPIDAPI_PROXY_SECRET=true`)

2. Bearer token (JWT)
- `Authorization: Bearer <token>`
- token is issued by `/auth/login` or `/auth/signup`

## How plan is resolved

1. If `Authorization: Bearer ...` is present:
- JWT is validated
- user is loaded from Redis
- plan comes from stored user record

2. If no bearer token:
- RapidAPI middleware validates headers
- plan comes from `x-rapidapi-subscription`
- invalid/missing plan defaults to `basic`

## Humanize request example

```http
POST /v1/humanize
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "Your source text...",
  "mode": "standard"
}
```

## Humanize response example

```json
{
  "success": true,
  "humanized_text": "...",
  "original_word_count": 120,
  "output_word_count": 128,
  "mode": "standard",
  "generation": {
    "provider_used": "anthropic",
    "model": "claude-3-5-sonnet-latest",
    "fallback_used": false,
    "fallback_reason": ""
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

If `fallback_used` is `true`, provider generation failed and local fallback rewriting was used.

## Usage endpoint response

`GET /v1/usage` (or `/usage`) returns current month usage:
- words used/limit/remaining
- requests used/limit/remaining
- plan limits and available modes

## Plans

- `basic`: 500 words/month, 500 requests/month, 500 words/request, mode `standard`
- `pro`: 10,000 words/month, 500,000 requests/month, 2,000 words/request, all modes
- `ultra`: 50,000 words/month, 500,000 requests/month, 5,000 words/request, all modes
- `mega`: 250,000 words/month, 500,000 requests/month, 15,000 words/request, all modes

## Modes

- `standard`
- `aggressive`
- `academic`
- `casual`

## Important environment variables

- `RAPIDAPI_PROXY_SECRET` (or `RAPIDAPI_SECRET`)
- `REQUIRE_RAPIDAPI_PROXY_SECRET`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (default `claude-3-5-sonnet-latest`)
- `ALLOW_LOCAL_FALLBACK` (`true` or `false`)
- `JWT_SECRET` (minimum 32 chars)
- `JWT_ALGORITHM`
- `JWT_EXPIRES_IN_HOURS`
- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`

## Errors

- `400` invalid input
- `401` unauthorized
- `403` mode not allowed for plan
- `408` timeout
- `429` rate limit or monthly quota exceeded
- `502` AI unavailable/error
- `503` backend unavailable
