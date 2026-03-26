# 🚀 AI Humanizer API — Undetectable AI Text Converter

Transform AI-generated text into natural, human-like writing — optimized for **RapidAPI developers, SaaS builders, and content platforms**.

---

## 🌐 Available on RapidAPI

This API is designed to run **exclusively via RapidAPI**, handling:
- Authentication
- Billing
- Rate limiting (per subscription)
- User management

👉 Simply subscribe and start using instantly.

---

## ✨ What This API Does

- Converts AI-written text → human-like text
- Improves readability & natural tone
- Helps reduce AI detection signals
- Supports multiple writing styles

---

## 🔥 Modes

| Mode       | Description |
|------------|------------|
| standard   | Balanced humanization |
| aggressive | Heavy rewriting |
| academic   | Formal tone |
| casual     | Conversational style |

---

## 💰 Subscription Tiers (Handled by RapidAPI)

| Plan   | Monthly Words | Per Request | Modes |
|--------|--------------|------------|------|
| Free   | 500          | 500        | Standard |
| Basic  | 10,000       | 2,000      | All |
| Pro    | 50,000       | 5,000      | All |
| Ultra  | 250,000      | 15,000     | All |

Server-side enforced via: `config.py` :contentReference[oaicite:0]{index=0}

---

## ⚡ Endpoint

### POST `/humanize`

---

## 📥 Request

### Headers (automatically handled by RapidAPI)
```http id="req-head"
x-rapidapi-key: YOUR_API_KEY
x-rapidapi-host: YOUR_API_HOST
