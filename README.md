# 🚀 AI Humanizer API — Undetectable AI Text Converter

Convert AI-generated text into natural, human-like writing.

Built for developers using RapidAPI.

---

## 🌐 RapidAPI Usage

This API is designed to be used via RapidAPI.

RapidAPI handles:
- Authentication
- Billing
- Subscriptions
- API key management

Just subscribe and start calling the API.

---

## ⚡ Endpoint

POST /humanize

---

## 📥 Request

### Headers (from RapidAPI)
x-rapidapi-key: YOUR_API_KEY  
x-rapidapi-host: YOUR_API_HOST  
x-rapidapi-proxy-secret: injected by RapidAPI proxy  

---

### Body

{
  "text": "Your AI-generated text here",
  "mode": "standard"
}

---

## 🔥 Modes

- standard → balanced rewrite  
- aggressive → heavy rewrite  
- academic → formal tone  
- casual → conversational tone  

---

## 💰 Plans

- Free → 500 words/month  
- Basic → 10,000 words/month  
- Pro → 50,000 words/month  
- Ultra → 250,000 words/month  

Limits are enforced server-side.

---

## 📤 Response

{
  "success": true,
  "humanized_text": "...",
  "original_word_count": 120,
  "output_word_count": 135,
  "mode": "standard",
  "quota": {
    "words_used": 500,
    "words_limit": 10000,
    "words_remaining": 9500
  }
}

---

## ⚠️ Errors

400 → invalid input  
401 → unauthorized  
403 → plan restriction  
408 → timeout  
429 → rate/quota exceeded  
502 → processing error  
503 → service unavailable  

---

## 🔒 Security

- Input sanitization (injection protection)
- Rate limiting per plan
- Atomic quota tracking
- Secure authentication middleware
- No stack trace leaks

---

## ⚡ Performance

- FastAPI (async)
- Redis-backed rate limiting
- Scalable & stateless

---

## 🎯 Use Cases

- AI rewriting tools  
- SaaS apps  
- SEO tools  
- blogging tools  
- student tools  

---

## 🚀 Start

1. Subscribe on RapidAPI  
2. Get your API key  
3. Call `/humanize`  
4. Done  

---

## 📜 License
MIT
