<div align="center">

# AI SIGNAL

### The Intelligence Briefing for AI Engineers

*Tracks AI/ML news across Hacker News · arXiv · NewsAPI · Medium · platformengineering.org · Platform Weekly*  
*Claude-powered summaries · Competitor analysis · Daily email digest*

---

**[Live Demo](#deployment) · [API Docs](#api-reference) · [Deploy in 10 min](#quick-deploy)**

</div>

---

## The Pitch

> **Every morning you open seven tabs, skim thirty headlines, and still feel like you missed something.**

AI Signal fixes that. One beautifully designed briefing lands in your inbox at 8 AM — curated from six sources engineers actually read, summarised by Claude, scored for relevance to *your* stack, and enriched with competitive intelligence on every new tool or model that matters.

It's not a newsletter you subscribed to and forgot. It's infrastructure you own.

**For platform engineers and software developers who need to stay sharp without losing half their morning to tab management.**

---

## Who Is This For?

| Persona | Problem Solved |
|---|---|
| **Platform / DevX Engineer** | Knows instantly which new AI tool threatens or enhances their current stack |
| **Engineering Manager** | Morning brief before standup — no research required |
| **ML Ops / AI Infra** | arXiv papers + production tool releases in one feed, relevance-ranked |
| **Tech Lead** | Competitor analysis for every product launch: are we behind? |
| **Independent Dev / Hacker** | Runs on ~$1/month with zero managed infrastructure |

---

## Feature Overview

| Feature | Details |
|---|---|
| **6 Sources** | Hacker News, arXiv, NewsAPI, Medium, platformengineering.org, Platform Weekly |
| **Claude Haiku Summaries** | 2–3 sentence digest per article, focused on engineering implications |
| **Competitor Analysis** | For every product/tool/model: lists rivals + *how this one differs* |
| **Relevance Scoring** | 1–10 score weighted toward Software Dev & Platform Engineering |
| **Auto Categorisation** | Product/Tool · AI Model · Research · News · Tutorial · Platform/Infra |
| **Hourly Refresh** | APScheduler fetches and processes new articles every 60 minutes |
| **Keep-Alive Cron** | cron-job.org pings `/health` every 10 minutes to prevent Render spin-down |
| **Daily Digest Email** | One HTML email per day at 08:00 UTC via Resend |
| **Editorial Dashboard** | Newspaper-style React UI — collapsible summaries, rival analysis, filters |
| **Multi-subscriber** | Up to 20 users, each with personal preferences and relevance thresholds |

---

## Network Architecture

```
 ╔══════════════════════════════════════════════════════════════════════════╗
 ║                        PUBLIC INTERNET                                   ║
 ╚══════════════════════════════════════════════════════════════════════════╝
        │                                              │
        │  HTTPS                                       │  HTTPS
        ▼                                              ▼
 ┌─────────────────────┐                    ┌──────────────────────┐
 │   React Frontend    │  REST API calls    │   FastAPI Backend    │
 │   (Static Site)     │ ──────────────────▶│   (Python 3.12)      │
 │                     │◀────────────────── │                      │
 │ Render.com          │   JSON responses   │ Render.com           │
 │ (free static)       │                    │ (free web service)   │
 └─────────────────────┘                    └──────────┬───────────┘
        │                                              │
        │  Browser renders                             │ Internal calls
        │  editorial UI                                │ (concurrent, async)
        ▼                                              │
 ┌─────────────────────┐                    ┌──────────▼───────────┐
 │   End User          │                    │   APScheduler        │
 │   (Chrome/Safari)   │                    │                      │
 │                     │                    │  ┌─────────────────┐ │
 │ • Reads digest UI   │                    │  │ Every 60 min    │ │
 │ • Subscribes via    │                    │  │ fetch_all_news()│ │
 │   drawer form       │                    │  └────────┬────────┘ │
 │ • Filters by cat    │                    │           │          │
 │ • Expands rival /   │                    │  ┌────────▼────────┐ │
 │   summary cards     │                    │  │ Daily @ 08:00   │ │
 └─────────────────────┘                    │  │ send_digest()   │ │
                                            │  └────────┬────────┘ │
                                            └───────────┼──────────┘
 ┌──────────────────────┐                              │
 │  cron-job.org        │  GET /health every 10 min    │
 │  (free keep-alive)   │ ────────────────────────────▶│
 └──────────────────────┘  prevents Render spin-down   │
                                                        │
       ┌────────────────────────────────────────────────┼────────────────────────────────┐
       │                  EXTERNAL APIs (all HTTPS, outbound only)                       │
       │                                                │                                │
       │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ ┌──────────────────┐  │
       │  │ Hacker News  │ │  arXiv.org   │ │  NewsAPI.org     │ │  Medium RSS      │  │
       │  │ Algolia API  │ │  Atom Feed   │ │  REST API        │ │  via rss2json    │  │
       │  │ (free)       │ │  (free)      │ │  (free tier)     │ │  (free proxy)    │  │
       │  └──────────────┘ └──────────────┘ └──────────────────┘ └──────────────────┘  │
       │                                                │                                │
       │  ┌──────────────┐ ┌──────────────┐ ┌──────────┴───────────────────────────┐   │
       │  │ platform     │ │ Platform     │ │          Claude API                  │   │
       │  │ engineering  │ │ Weekly RSS   │ │     (Anthropic — claude-haiku)       │   │
       │  │ .org RSS     │ │ (free)       │ │  Summarise + Categorise + Rivals     │   │
       │  │ (free)       │ └──────────────┘ └──────────────────────────────────────┘   │
       │  └──────────────┘                                                              │
       └────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                                            ┌───────────▼──────────┐
                                            │   Resend Email API   │
                                            │   Free: 3k/month     │
                                            └───────────┬──────────┘
                                                        │ SMTP/TLS
                                                        ▼
                                            ┌──────────────────────┐
                                            │  Subscriber Inboxes  │
                                            │  (up to 20 users)    │
                                            └──────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                              DATA LAYER                                      │
 │                                                                              │
 │   SQLite (aiosqlite) · ephemeral on /tmp — articles re-fetched hourly        │
 │   Subscribers seeded from SEED_SUBSCRIBERS env var on every restart          │
 │                                                                              │
 │   articles ────────────── users ──────────── digest_log                     │
 │   (id, title, url,         (email, name,      (sent_at,                     │
 │    source, summary,         prefs, active)     recipient, count)             │
 │    category, tags,                                                           │
 │    competitors,                                                              │
 │    relevance_score)                                                          │
 │                                                                              │
 │   No managed DB · No Redis · No message queue · Zero ops overhead            │
 └──────────────────────────────────────────────────────────────────────────────┘

SECURITY BOUNDARIES
═══════════════════
  • All external API calls: outbound HTTPS only, no inbound ports opened
  • Frontend → Backend: CORS configured on backend
  • API keys stored as Render environment variables — never in code or DB
  • Render provides TLS termination — no self-managed certs needed
  • Email delivery via Resend (SPF/DKIM handled by Resend)

DATA FLOW SEQUENCE (every hour)
════════════════════════════════
  1. APScheduler triggers fetch_all_news()
  2. 6 async tasks launched concurrently (HN + arXiv + NewsAPI + Medium + PE.org + PW)
  3. Raw articles deduplicated by URL hash
  4. Content enrichment: og:description fetched for articles with no body text
  5. Batches of 5 sent to Claude Haiku (summarise + categorise + rival analysis)
  6. Results upserted to SQLite (ON CONFLICT — no duplicates)
  7. At 08:00 UTC: top articles pulled, HTML email built per subscriber
  8. Resend API delivers personalised digest to each inbox
  9. digest_log entry written for audit trail
```

---

## Deployment (Render.com)

The repo includes `render.yaml` for one-click Blueprint deploy — both frontend and backend provision automatically.

```bash
# 1. Fork this repo to your GitHub account

# 2. Go to https://render.com → New → Blueprint
#    Connect your GitHub repo — Render reads render.yaml automatically

# 3. Set these env vars in the Render dashboard:
#    ANTHROPIC_API_KEY=sk-ant-...
#    RESEND_API_KEY=re_...
#    NEWS_API_KEY=...
#    FROM_EMAIL=AI Signal <onboarding@resend.dev>
#    SEED_SUBSCRIBERS=YourName:you@email.com
#    PYTHON_VERSION=3.12.0

# 4. Click Deploy. Both services go live with public HTTPS URLs.
```

Your app will be live at:
- **Frontend**: `https://ai-signal-frontend.onrender.com`
- **Backend API**: `https://ai-signal-backend.onrender.com`
- **API Docs**: `https://ai-signal-backend.onrender.com/docs`

---

## Keep-Alive Cron (Required for Free Tier)

Render's free tier spins down web services after 15 minutes of inactivity, causing a cold-start delay on the next request. A keep-alive cron job prevents this.

**Setup (already configured for this deployment):**

1. Go to **[cron-job.org](https://cron-job.org)** — free account, no card
2. Create a new cron job:
   - **URL**: `https://ai-signal-backend.onrender.com/health`
   - **Schedule**: Every 10 minutes
   - **Method**: GET
3. Save — the service now stays warm 24/7

The `/health` endpoint returns `{"status": "healthy"}` and costs nothing to call. With the cron running, the backend responds instantly at all times and the hourly news refresh never misses a cycle due to spin-down.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/news` | Articles (params: `category`, `source`, `min_relevance`, `search`, `limit`, `offset`) |
| `GET` | `/api/news/stats` | Counts by category |
| `GET` | `/api/news/categories` | Category list |
| `GET` | `/api/news/sources` | Source list |
| `GET` | `/api/users` | All subscribers |
| `POST` | `/api/users` | Add subscriber `{email, name, min_relevance, categories}` |
| `DELETE` | `/api/users/{email}` | Remove subscriber |
| `GET` | `/api/config` | Check which API keys are configured |
| `GET` | `/api/config/debug-claude` | Test Claude API connection live |
| `POST` | `/api/trigger-refresh` | Manual news refresh |
| `POST` | `/api/trigger-digest` | Manual digest send |
| `GET` | `/health` | Health check — used by keep-alive cron |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Cost Breakdown

| Service | Free Tier | Estimated Monthly Use | Cost |
|---|---|---|---|
| Render (backend) | 750 hr/month | ~720 hr | **$0** |
| Render (frontend) | Unlimited static | — | **$0** |
| Resend (email) | 3,000 emails/month | ~300 (20 users) | **$0** |
| NewsAPI | 100 req/day | ~6 req/day | **$0** |
| HN Algolia API | Unlimited | — | **$0** |
| arXiv API | Unlimited | — | **$0** |
| Medium RSS (rss2json) | 10k req/month | ~720 | **$0** |
| platformengineering.org RSS | Unlimited | — | **$0** |
| Platform Weekly RSS | Unlimited | — | **$0** |
| cron-job.org | Free | 4,320 pings/month | **$0** |
| Claude Haiku | $0.25/1M input tokens | ~500 articles × ~500 tokens | **~$1.50/month** |
| **TOTAL** | | | **~$1–2/month** |

---

## Configuration Reference

```bash
# Render Environment Variables

# Required
ANTHROPIC_API_KEY=sk-ant-...          # Claude Haiku for AI analysis
RESEND_API_KEY=re_...                  # Email delivery (resend.com)
FROM_EMAIL=AI Signal <onboarding@resend.dev>
PYTHON_VERSION=3.12.0                  # Pin Python — avoids build failures

# Strongly recommended
NEWS_API_KEY=...                       # newsapi.org free key (100 req/day)

# Subscriber seeding — survives ephemeral filesystem restarts
# Format: "Name1:email1@x.com,Name2:email2@x.com"
SEED_SUBSCRIBERS=Alice:alice@example.com

# App settings
APP_URL=https://ai-signal-frontend.onrender.com
DB_PATH=/tmp/news_tracker.db          # Ephemeral — fine, articles re-fetched hourly
```

---

## Extending the App

**Add keywords** (`news_fetcher.py`):
```python
AI_KEYWORDS = ["your-technology", "your-company", ...]
```

**Change refresh cadence** (`main.py`):
```python
scheduler.add_job(refresh_news_job, "interval", hours=2)
scheduler.add_job(send_digest_job, "cron", hour=7, minute=30)
```

**Add a source** (`news_fetcher.py`): implement an async function returning `List[RawArticle]`, add it to the `gather()` call in `fetch_all_news()`.

---

## Tech Stack

```
Backend          Python 3.12 · FastAPI · APScheduler · aiosqlite · aiohttp
AI               Anthropic Claude Haiku (claude-haiku-4-5-20251001)
Email            Resend API (free tier: 3,000/month)
Database         SQLite on /tmp — ephemeral, zero ops
News Sources     HN Algolia · arXiv · NewsAPI · Medium RSS · platformengineering.org · Platform Weekly
Frontend         React 18 · Vite · Custom editorial CSS (no component library)
Typography       Playfair Display · Source Serif 4 · Barlow Condensed
Hosting          Render.com — backend (free web service) + frontend (free static site)
Keep-Alive       cron-job.org — pings /health every 10 min to prevent spin-down
IaC              render.yaml included for one-click Blueprint deploy
```
