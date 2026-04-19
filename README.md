# AI Humanizer API

Convert AI-generated text into more natural writing with per-plan limits and authentication.

## Endpoints

- `POST /humanize`
- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `GET /health`

## Auth Modes

`/humanize` accepts two auth styles:

1. RapidAPI headers
- `x-rapidapi-key`
- `x-rapidapi-host`
- `x-rapidapi-subscription` (plan from RapidAPI)
- optional `x-rapidapi-user`
- optional `x-rapidapi-proxy-secret` (required only if enabled by env)

2. JWT bearer token
- `Authorization: Bearer <token>`
- token comes from `/auth/login` or `/auth/signup`

## Which plan is used

1. If `Authorization: Bearer ...` is present:
- Token is decoded (`JWT_SECRET`, `JWT_ALGORITHM`)
- User is loaded from Redis
- Plan comes from stored user record (`user.plan`)

2. If no bearer token:
- RapidAPI middleware validates standard RapidAPI headers
- Plan comes from `x-rapidapi-subscription`
- Unknown plans are downgraded to `free`

## JWT details

Access token payload:
- `userId`
- `iat` (issued-at unix timestamp)
- `exp` (expiry unix timestamp)

Config:
- `JWT_SECRET` (required)
- `JWT_ALGORITHM` (default `HS256`)
- `JWT_EXPIRES_IN_HOURS` (default `24`)

## Request example

```http
POST /humanize
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "Your source text...",
  "mode": "standard"
}
```

## Response example

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
    "words_remaining": 9500
  }
}
```

If `fallback_used` is `true`, AI provider failed and local fallback logic was used.

## Plans

- `free`: 500 words/month, 500 words/request, mode `standard`
- `basic`: 10,000 words/month, 2,000 words/request, all modes
- `pro`: 50,000 words/month, 5,000 words/request, all modes
- `ultra`: 250,000 words/month, 15,000 words/request, all modes

## Modes

- `standard`
- `aggressive`
- `academic`
- `casual`

## Validate current JWT user

Use `GET /auth/me` with bearer token to confirm:
- current user id
- email
- active plan
- allowed modes
- monthly/per-request limits

## Important environment variables

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (optional, default `claude-3-5-sonnet-latest`)
- `ALLOW_LOCAL_FALLBACK` (`true` or `false`)
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `JWT_EXPIRES_IN_HOURS`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `UPSTASH_REDIS_URL` (rate limiter backend)
- `REQUIRE_RAPIDAPI_PROXY_SECRET`
- `RAPIDAPI_PROXY_SECRET` or `RAPIDAPI_SECRET`

## Errors

- `400` invalid input
- `401` unauthorized
- `403` mode not allowed for plan
- `408` timeout
- `429` rate or monthly quota exceeded
- `502` AI error/unavailable
- `503` backend unavailable
