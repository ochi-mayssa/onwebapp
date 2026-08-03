API integration guide for services processors

Overview

This document lists environment variables the app checks and shows minimal example request/response shapes to implement "real" results for the services processors. Processors fall back to simulated results when no API is configured or the request fails.

Required dependency

- `requests` must be installed (added to `requirements.txt`).

Environment variables (examples)

- INDUSTRIAL_API_URL - POST endpoint that accepts JSON {"identifier": "..."}
- INDUSTRIAL_API_KEY - (optional) bearer token

- PREDICTIVE_MAINTENANCE_API - POST endpoint that accepts JSON {"identifier": "..."}
- PREDICTIVE_MAINTENANCE_KEY - (optional) bearer token

- MARKET_DATA_API - GET endpoint that accepts `company` param
- MARKET_DATA_KEY - (optional) bearer token

- PAGESPEED_API_URL - GET endpoint that accepts `url` param
- PAGESPEED_API_KEY - (optional) bearer token

- SOCIAL_API_URL - GET endpoint that accepts `handle` param
- SOCIAL_API_KEY - (optional) bearer token

- LINK_CRAWLER_API - GET endpoint that accepts `url` param and returns `broken_links`

- KEYWORD_API_URL - GET endpoint that accepts `query` param
- KEYWORD_API_KEY - (optional) bearer token

Minimal expected JSON response examples

1) Industrial diagnostics (POST):
{
  "identifier": "MACHINE_001",
  "health_score": 78,
  "status": "healthy",
  "issues": [],
  "chart": {"labels": ["Q1","Q2"], "values": [70,78], "title":"Health"}
}

2) Predictive maintenance (POST):
{
  "identifier": "PUMP_01",
  "failure_probability": 12.3,
  "risk_level": "low",
  "recommended_maintenance_in_days": 30,
  "chart": { ... }
}

3) Market data (GET):
{
  "company": "Acme",
  "annual_revenue": 5000000,
  "market_share": "8%",
  "chart": {...}
}

4) PageSpeed/SEO (GET):
{
  "url": "https://example.com",
  "seo_score": 82,
  "top_keywords": [{"keyword":"example service","rank":12}],
  "chart": {...}
}

5) Social analytics (GET):
{
  "handle": "@acct",
  "total_followers": 12000,
  "platforms": {"Twitter": {"followers":5000}},
  "chart": {...}
}

6) Link crawler (GET):
{
  "url": "https://example.com",
  "broken_links": ["https://example.com/missing.png"]
}

7) Keyword API (GET):
{
  "query": "industrial automation sensors",
  "suggested_keywords": ["industrial automation sensors best", "industrial automation sensors 2026"],
  "chart": {"labels": [...], "values": [...], "title": "Interest Over Time"}
}

Tips to test locally

- Create a `.env` file or export env vars before running dev server. Example `.env` (using python-dotenv or set in your shell):

INDUSTRIAL_API_URL=https://your-api.example.com/industrial
INDUSTRIAL_API_KEY=sk_test_...
KEYWORD_API_URL=https://your-api.example.com/keywords
KEYWORD_API_KEY=sk_test_...

- Restart the dev server after setting env vars.

- Example curl to exercise keyword endpoint (replace with your URL):

curl -G 'https://your-api.example.com/keywords' --data-urlencode "query=industrial automation sensors" -H "Authorization: Bearer sk_test_..."

Notes

- Processors include safe fallbacks so the platform remains functional without APIs.
- If you want, I can implement an adapter for a specific provider (e.g., Google Pagespeed, Semrush, Ahrefs) — tell me which provider and I will add an example adapter and tests.
