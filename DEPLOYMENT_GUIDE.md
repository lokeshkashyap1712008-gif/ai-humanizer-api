# AI Humanizer API Deployment Guide

This service is split into two parts:

1. `FastAPI` app for auth, quota tracking, and text generation
2. `Cloudflare Worker` as the public proxy layer for RapidAPI

Use Python `3.11.15` for the API runtime.

## 1. What you need before launch

- Python `3.11.15`
- Node.js `20+`
- A production Redis instance:
  - `UPSTASH_REDIS_URL`
  - `UPSTASH_REDIS_REST_URL`
  - `UPSTASH_REDIS_REST_TOKEN`
- An Anthropic API key for Claude
- A strong JWT secret, minimum 32 characters
- A strong RapidAPI proxy secret, minimum 32 characters
- A deployed HTTPS URL for the FastAPI app
- A Cloudflare account with Workers enabled
- A RapidAPI API entry ready to point at the Worker URL

## 2. Environment variables for the FastAPI app

Set these in production:

```env
APP_ENV=production
STRICT_EXTERNALS=true

RAPIDAPI_PROXY_SECRET=replace-with-a-long-random-secret
REQUIRE_RAPIDAPI_PROXY_SECRET=true

JWT_SECRET=replace-with-a-very-long-random-secret
JWT_ALGORITHM=HS256
JWT_EXPIRES_IN_HOURS=24

ANTHROPIC_API_KEY=replace-with-your-anthropic-key
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ALLOW_LOCAL_FALLBACK=false

UPSTASH_REDIS_URL=replace-with-upstash-redis-url
UPSTASH_REDIS_REST_URL=replace-with-upstash-rest-url
UPSTASH_REDIS_REST_TOKEN=replace-with-upstash-rest-token

MAX_BODY_SIZE=51200
REQUEST_TIMEOUT=30
ALLOWED_ORIGINS=*
```

Notes:

- `STRICT_EXTERNALS=true` makes startup fail if Redis or Claude config is missing.
- `ALLOW_LOCAL_FALLBACK=false` is the safer RapidAPI launch setting if you do not want silent non-Claude responses.
- Rotate any secret that has ever been committed to `.env` or shared in plain text.

## 3. Local setup

Create a virtual environment and install dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python3.11 -m pip install --upgrade pip
python3.11 -m pip install -r requirements.txt
```

Start the API locally:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Quick checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/plan
```

## 4. How to use the API

### Sign up

```bash
curl -X POST http://127.0.0.1:8000/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "team@example.com",
    "password": "SuperSecurePassword123!",
    "plan": "pro"
  }'
```

### Log in

```bash
curl -X POST http://127.0.0.1:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "team@example.com",
    "password": "SuperSecurePassword123!"
  }'
```

### Call humanize with JWT

```bash
curl -X POST http://127.0.0.1:8000/v1/humanize \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is the source text that should be made less robotic.",
    "mode": "standard"
  }'
```

### Call humanize with RapidAPI-style headers

```bash
curl -X POST http://127.0.0.1:8000/v1/humanize \
  -H "x-rapidapi-key: demo-key" \
  -H "x-rapidapi-host: your-api-host" \
  -H "x-rapidapi-user: demo-user" \
  -H "x-rapidapi-subscription: pro" \
  -H "x-rapidapi-proxy-secret: YOUR_PROXY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is the source text that should be made less robotic.",
    "mode": "academic"
  }'
```

### Read current usage

```bash
curl http://127.0.0.1:8000/v1/usage \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Validate a user token and plan

This is the fastest live check for a user:

```bash
curl http://127.0.0.1:8000/v1/auth/me \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Expected response shape:

```json
{
  "success": true,
  "user": {
    "userId": "user-id",
    "email": "team@example.com",
    "plan": "pro"
  },
  "rights": {
    "modes": ["academic", "aggressive", "casual", "standard"],
    "monthly_words": 10000,
    "monthly_requests": 500000,
    "per_request_words": 2000
  }
}
```

This confirms all of the following in one shot:

1. the JWT is valid
2. the user exists in Redis
3. the stored plan is readable
4. the plan rights map is being applied correctly

## 5. Cloudflare Worker setup

Install Worker dependencies:

```bash
cd ai-humanizer-worker
npm install
```

For local Worker development:

```bash
npm run dev
```

Set the backend URL secret in Cloudflare:

```bash
wrangler secret put FASTAPI_BASE_URL
```

Use your deployed FastAPI URL as the value, for example:

```text
https://your-fastapi-domain.example.com
```

Deploy the Worker:

```bash
npm run deploy
```

The Worker simply forwards requests to the FastAPI backend and adds CORS headers.

## 6. RapidAPI launch wiring

Use the Cloudflare Worker URL as the public endpoint in RapidAPI.

Recommended flow:

1. Deploy FastAPI behind HTTPS
2. Deploy Worker with `FASTAPI_BASE_URL` pointing to FastAPI
3. Configure RapidAPI to send traffic to the Worker URL
4. Add `x-rapidapi-proxy-secret` in the Worker or gateway flow if you require proxy verification
5. Verify `x-rapidapi-subscription` maps cleanly to `basic`, `pro`, `ultra`, or `mega`

Before go-live, run these checks:

1. `GET /health` returns `200`
2. `GET /v1/plan` returns plan metadata
3. signup/login works with a valid JWT secret
4. `/v1/humanize` succeeds with Claude
5. `/v1/usage` reflects counters in Redis
6. invalid plan requests are downgraded to `basic`
7. invalid proxy secret returns `401`
8. monthly quota overflow returns `429`

## 7. Test commands

Run the Python test suite:

```bash
python3.11 -m pytest
```

Run the Worker test suite:

```bash
cd ai-humanizer-worker
npm test
```

## 8. User validation and admin checks

### How users are stored

Each signup creates:

1. an email lookup key:
   `auth:user:email:<sha256-of-lowercase-email>`
2. a user document:
   `auth:user:id:<user_id>`

The user document contains:

- `user_id`
- `email`
- `password_hash`
- `plan`
- `created_at`

### Validate that a signup worked

1. Call `POST /v1/auth/signup`
2. Save the returned JWT
3. Call `GET /v1/auth/me` with that JWT
4. Call `GET /v1/usage` with that JWT

If both calls succeed, the user record and plan are wired correctly.

### Check a user and their plan from Redis

Use the admin script:

```bash
python3.11 scripts/user_admin.py by-email team@example.com
python3.11 scripts/user_admin.py by-id USER_ID_HERE
python3.11 scripts/user_admin.py list --limit 20
```

This script requires:

```bash
export UPSTASH_REDIS_URL='your-redis-connection-url'
```

### Change or verify plan values

Current valid plans are:

- `basic`
- `pro`
- `ultra`
- `mega`

To verify a user plan:

1. inspect the stored user document with `scripts/user_admin.py`
2. confirm `plan` matches one of the valid plan names
3. call `/v1/auth/me` and check the `rights` block

That gives you both the raw stored value and the effective runtime rights.

## 9. Production recommendations

- Keep docs disabled in production unless you intentionally expose them
- Use managed process hosting for FastAPI with health checks and restart policy
- Put FastAPI behind HTTPS only
- Rotate all committed or shared secrets before launch
- Keep `ALLOW_LOCAL_FALLBACK=false` for predictable paid behavior
- Monitor:
  - Redis failures
  - Claude timeout rate
  - `429`, `502`, and `503` error volume
  - request latency by plan
