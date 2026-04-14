# AI Humanizer API — Undetectable AI Text Converter

Convert AI-generated text into natural, human-like writing.

Built for RapidAPI with word + request quota tracking.

---

## RapidAPI Usage

This API is designed to be used via **RapidAPI**.

RapidAPI handles:
- Authentication (API Keys)
- Billing & Subscriptions
- API key management

Just subscribe and start calling the API.

---

## Endpoints

### Core
- `POST /humanize` - Convert AI text to human-like text
- `GET /usage` - Check your current quota usage
- `GET /plan` - View all available plans and limits
- `GET /health` - Health check

### Authentication (Alternative to RapidAPI headers)
- `POST /auth/signup` - Create account
- `POST /auth/login` - Get Bearer token

---

## Authentication

### Method 1: RapidAPI (Recommended)
Use RapidAPI's injected headers:
```
x-rapidapi-key: YOUR_API_KEY
x-rapidapi-host: YOUR_API_HOST
x-rapidapi-proxy-secret: (injected by RapidAPI)
x-rapidapi-subscription: basic|pro|ultra|mega
```

### Method 2: Bearer Token
```
Authorization: Bearer <token-from-login>
```

---

## POST /humanize

### Request Body

```json
{
  "text": "Your AI-generated text here",
  "mode": "standard"
}
```

### Response

```json
{
  "success": true,
  "humanized_text": "...",
  "original_word_count": 120,
  "output_word_count": 135,
  "mode": "standard",
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

### Response Headers

```
X-Ratelimit-Limit: 500000
X-Ratelimit-Remaining: 499975
X-Ratelimit-Reset: 1735689600
```

---

## GET /usage

Check your current month's usage.

### Response

```json
{
  "plan": "pro",
  "period": "2026-04",
  "quotas": {
    "words": {
      "used": 5000,
      "limit": 10000,
      "remaining": 5000
    },
    "requests": {
      "used": 42,
      "limit": 500000,
      "remaining": 499958
    }
  },
  "limits": {
    "per_request_words": 2000,
    "available_modes": ["standard", "aggressive", "academic", "casual"]
  }
}
```

---

## Modes

| Mode | Description |
|------|-------------|
| `standard` | Balanced rewrite (available on all plans) |
| `aggressive` | Heavy rewrite |
| `academic` | Formal tone |
| `casual` | Conversational tone |

---

## Plans

| Plan | Monthly Words | Monthly Requests | Per-Request Max | Modes | Priority | Bulk |
|------|---------------|------------------|-----------------|-------|----------|------|
| **Basic** | 500 | 500 | 500 | standard | No | No |
| **Pro** | 10,000 | 500,000 | 2,000 | All | No | No |
| **Ultra** | 50,000 | 500,000 | 5,000 | All | Yes | No |
| **Mega** | 250,000 | 500,000 | 15,000 | All | Yes | Yes |

**Note**: Both word AND request quotas are enforced server-side.

---

## Rate Limits (Per Minute)

| Plan | Limit |
|------|-------|
| Basic | 5 requests/minute |
| Pro | 20 requests/minute |
| Ultra | 60 requests/minute |
| Mega | 120 requests/minute |

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Invalid input |
| 401 | Unauthorized / Invalid plan |
| 403 | Mode not allowed for plan |
| 408 | Request timeout |
| 429 | Rate limit or quota exceeded |
| 502 | AI processing error |
| 503 | Service unavailable |

---

## License

MIT
