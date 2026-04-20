# AI Humanizer API Deployment Guide

This service has two layers:

1. FastAPI backend for auth checks, quotas, and text generation
2. Cloudflare Worker as the public RapidAPI-facing proxy

The API is RapidAPI-header authenticated only.

## 1. Prerequisites

- Python `3.11.x`
- Node.js `20+`
- Redis (Upstash recommended):
  - `UPSTASH_REDIS_URL`
  - `UPSTASH_REDIS_REST_URL`
  - `UPSTASH_REDIS_REST_TOKEN`
- Anthropic API key
- RapidAPI proxy secret (min 32 chars recommended)
- HTTPS host for FastAPI
- Cloudflare account (Workers enabled)

## 2. FastAPI Environment Variables

Use these in production:

```env
APP_ENV=production
STRICT_EXTERNALS=true

RAPIDAPI_PROXY_SECRET=replace-with-a-long-random-secret
REQUIRE_RAPIDAPI_PROXY_SECRET=true

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
- `RAPIDAPI_SECRET` is also accepted as a legacy alias for `RAPIDAPI_PROXY_SECRET`.
- Keep `ALLOW_LOCAL_FALLBACK=false` in production if you only want provider-backed output.

## 3. Local Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python3.11 -m pip install --upgrade pip
python3.11 -m pip install -r requirements.txt
```

Run API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Quick checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/plan
```

## 4. API Usage

### Humanize

```bash
curl -X POST http://127.0.0.1:8000/v1/humanize \
  -H "x-rapidapi-key: demo-key" \
  -H "x-rapidapi-user: demo-user" \
  -H "x-rapidapi-subscription: pro" \
  -H "x-rapidapi-proxy-secret: YOUR_PROXY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is the source text that should be made less robotic.",
    "mode": "academic"
  }'
```

### Usage

```bash
curl http://127.0.0.1:8000/v1/usage \
  -H "x-rapidapi-key: demo-key" \
  -H "x-rapidapi-user: demo-user" \
  -H "x-rapidapi-subscription: pro" \
  -H "x-rapidapi-proxy-secret: YOUR_PROXY_SECRET"
```

## 5. Cloudflare Worker Setup

```bash
cd ai-humanizer-worker
npm install
npm run dev
```

Set backend URL in Worker secrets:

```bash
wrangler secret put FASTAPI_BASE_URL
```

Deploy Worker:

```bash
npm run deploy
```

## 6. RapidAPI Wiring

Use Worker URL as your public RapidAPI endpoint.

Recommended:
1. Deploy FastAPI with HTTPS
2. Deploy Worker with `FASTAPI_BASE_URL`
3. Configure RapidAPI to route to Worker URL
4. Ensure Worker forwards:
   - `x-rapidapi-key`
   - `x-rapidapi-user`
   - `x-rapidapi-subscription`
   - `x-rapidapi-proxy-secret`

## 7. Validation Checklist

1. `GET /health` returns `200`
2. `GET /v1/plan` returns plan metadata
3. `POST /v1/humanize` works with valid RapidAPI headers
4. `GET /v1/usage` reflects Redis counters
5. Invalid proxy secret returns `401`
6. Monthly quota overflow returns `429`

## 8. Tests

API tests:

```bash
python3.11 -m pytest
```

Worker tests:

```bash
cd ai-humanizer-worker
npm test
```
