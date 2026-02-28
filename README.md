<div align="center">

# AI SIGNAL

### The Intelligence Briefing for AI Engineers

*Tracks AI/ML news across Hacker News · arXiv · NewsAPI · Medium*  
*Claude-powered summaries · Competitor analysis · Daily email digest*

---

**[Live Demo](#deployment) · [API Docs](#api-reference) · [Deploy in 10 min](#quick-deploy)**

</div>

---

## The Pitch

> **Every morning you open seven tabs, skim thirty headlines, and still feel like you missed something.**

AI Signal fixes that. One beautifully designed briefing lands in your inbox at 8 AM — curated from the four sources engineers actually read, summarised by Claude, scored for relevance to *your* stack, and enriched with competitive intelligence on every new tool or model that matters.

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
| **Independent Dev / Hacker** | Runs on $1/month with zero managed infrastructure |

---

## Feature Overview

| Feature | Details |
|---|---|
| **4 Sources** | Hacker News (scored), arXiv (papers), NewsAPI (press), Medium (community) |
| **Claude Haiku Summaries** | 2–3 sentence digest per article, focused on engineering implications |
| **Competitor Analysis** | For every product/tool/model: lists rivals + *how this one differs* |
| **Relevance Scoring** | 1–10 score weighted toward Software Dev & Platform Engineering |
| **Auto Categorisation** | Product/Tool · AI Model · Research · News · Tutorial · Platform/Infra |
| **Hourly Refresh** | APScheduler fetches and processes new articles every 60 minutes |
| **Daily Digest Email** | One beautiful HTML email per day at 08:00 UTC via Resend |
| **Editorial Dashboard** | Newspaper-style React UI with filters, search, and expandable rival cards |
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
 │ Render / Vercel     │   JSON responses   │ Render / Fly.io      │
 │ cdn.render.com      │                    │ api.yourdomain.com   │
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
 │ • Expands rival     │                    │  ┌────────▼────────┐ │
 │   analysis          │                    │  │ Daily @ 08:00   │ │
 └─────────────────────┘                    │  │ send_digest()   │ │
                                            │  └────────┬────────┘ │
                                            └───────────┼──────────┘
                                                        │
              ┌─────────────────────────────────────────┼──────────────────────────────┐
              │             EXTERNAL APIs (all HTTPS, outbound only)                   │
              │                                         │                              │
              │  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────────┐  │
              │  │  Hacker News     │  │  arXiv.org     │  │  NewsAPI.org         │  │
              │  │  Algolia API     │  │  Atom Feed     │  │  REST API            │  │
              │  │  (free, no key)  │  │  (free, no key)│  │  (free tier)         │  │
              │  └──────────────────┘  └────────────────┘  └──────────────────────┘  │
              │                                         │                              │
              │  ┌──────────────────┐  ┌────────────────┴──────────────────────────┐  │
              │  │  Medium RSS      │  │               Claude API                  │  │
              │  │  via rss2json    │  │          (Anthropic — claude-haiku)        │  │
              │  │  (free proxy)    │  │  Summarise + Categorise + Rival analysis  │  │
              │  └──────────────────┘  └───────────────────────────────────────────┘  │
              └─────────────────────────────────────────────────────────────────────────┘
                                                        │
                                            ┌───────────▼──────────┐
                                            │   Resend Email API   │
                                            │   (SMTP alternative) │
                                            │   Free: 3k/month     │
                                            └───────────┬──────────┘
                                                        │ SMTP/TLS
                                                        ▼
                                            ┌──────────────────────┐
                                            │  Subscriber Inboxes  │
                                            │  (up to 20 users)    │
                                            │  Gmail / Outlook /   │
                                            │  Corporate email     │
                                            └──────────────────────┘

 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           DATA LAYER                                        │
 │                                                                             │
 │   ┌─────────────────────────────────────────────────────┐                  │
 │   │              SQLite (aiosqlite)                      │                  │
 │   │              Mounted at /app/data/                   │                  │
 │   │                                                      │                  │
 │   │  articles ──────────── users ──────── digest_log     │                  │
 │   │  (id, title, url,      (email, name,  (sent_at,      │                  │
 │   │   source, summary,      prefs, active) recipient,    │                  │
 │   │   category, tags,                      count)        │                  │
 │   │   competitors,                                       │                  │
 │   │   relevance_score)                                   │                  │
 │   └─────────────────────────────────────────────────────┘                  │
 │                                                                             │
 │   No managed DB needed. No Redis. No message queue. SQLite handles          │
 │   10-20 users and ~500 articles/day with zero operational overhead.          │
 └─────────────────────────────────────────────────────────────────────────────┘

SECURITY BOUNDARIES
═══════════════════
  • All external API calls: outbound HTTPS only, no inbound ports opened
  • Frontend → Backend: CORS-restricted to known origin
  • API keys stored as environment variables, never in code or DB
  • No authentication required for read endpoints (private deployment)
  • Render/Fly.io provide TLS termination — no self-managed certs
  • Email delivery via Resend (SPF/DKIM handled by them)

DATA FLOW SEQUENCE (every hour)
════════════════════════════════
  1. APScheduler triggers fetch_all_news()
  2. 4 async tasks launched concurrently (HN + arXiv + NewsAPI + Medium)
  3. Raw articles deduplicated by URL hash
  4. Batches of 5 sent to Claude Haiku (summarise + categorise + rivals)
  5. Results upserted to SQLite (ON CONFLICT — no duplicates)
  6. At 08:00 UTC: top articles pulled, HTML email built per user
  7. Resend API delivers to subscriber inboxes
  8. digest_log entry written for audit
```

---

## Quick Deploy (Public Internet, ~10 min)

### Option A: Render.com — Recommended (free)

The repo includes a `render.yaml` for one-click infrastructure-as-code deploy.

```bash
# 1. Fork this repo to your GitHub account

# 2. Go to https://render.com → New → Blueprint
#    Connect your GitHub repo — Render reads render.yaml automatically

# 3. Set these env vars in the Render dashboard:
#    ANTHROPIC_API_KEY=sk-ant-...
#    RESEND_API_KEY=re_...
#    NEWS_API_KEY=...             (optional)
#    FROM_EMAIL=AI Signal <you@yourdomain.com>
#    APP_URL=https://ai-signal-frontend.onrender.com

# 4. Click Deploy. Both services go live with HTTPS URLs.
```

Your app will be live at:
- **Frontend**: `https://ai-signal-frontend.onrender.com`
- **Backend API**: `https://ai-signal-backend.onrender.com`
- **API Docs**: `https://ai-signal-backend.onrender.com/docs`

> ⚠️ **Render free tier spins down after 15 min inactivity.** To keep it warm, set up a free cron at [cron-job.org](https://cron-job.org) to ping `https://ai-signal-backend.onrender.com/health` every 10 minutes.

---

### Option B: Fly.io (always-on, still free)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Authenticate
fly auth login

# Launch backend (fly.toml included)
cd ai-news-tracker
fly launch --config fly.toml --name ai-signal-backend

# Set secrets
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set RESEND_API_KEY=re_...
fly secrets set NEWS_API_KEY=...

# Create persistent volume for SQLite
fly volumes create ai_signal_data --size 1 --region sin

fly deploy

# Deploy frontend to Vercel (free, always-on)
cd frontend
npx vercel --prod
# Set VITE_API_URL=https://ai-signal-backend.fly.dev during prompts
```

---

### Option C: Docker (Self-hosted / VPS)

```bash
# On any VPS (Hetzner CX11 = €4/month, DigitalOcean Droplet = $6/month)
git clone https://github.com/you/ai-news-tracker
cd ai-news-tracker
cp backend/.env.example backend/.env
# Fill in your keys

docker-compose up -d

# Add HTTPS with Caddy (automatic TLS)
apt install -y caddy
cat > /etc/caddy/Caddyfile << 'EOF'
your-domain.com {
  reverse_proxy localhost:3000
}
api.your-domain.com {
  reverse_proxy localhost:8000
}
EOF
systemctl restart caddy
```

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
| `POST` | `/api/trigger-refresh` | Manual news refresh |
| `POST` | `/api/trigger-digest` | Manual digest send |
| `GET` | `/health` | Health check (used by uptime monitors) |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Cost Breakdown

| Service | Free Tier | Estimated Monthly Use | Cost |
|---|---|---|---|
| Render (backend) | 750 hr/month | ~720 hr | **$0** |
| Render (frontend) | Unlimited static | — | **$0** |
| Resend (email) | 3,000 emails/month | ~300 (20 users × 15 days) | **$0** |
| NewsAPI | 100 req/day | ~24/day | **$0** |
| HN Algolia API | Unlimited | — | **$0** |
| arXiv API | Unlimited | — | **$0** |
| Medium RSS via rss2json | 10k req/month | ~720 | **$0** |
| Claude Haiku | $0.25/1M input tokens | ~500 articles × ~400 tokens | **~$1.20/month** |
| **TOTAL** | | | **~$1–2/month** |

> **To get to $0 total**: set `max_results=5` per arXiv/HN query and only process top 20 articles per refresh. Claude cost drops to ~$0.25/month.

---

## Configuration Reference

```bash
# backend/.env

# Required
ANTHROPIC_API_KEY=sk-ant-...     # Claude Haiku for AI analysis
RESEND_API_KEY=re_...             # Email delivery (resend.com)
FROM_EMAIL=AI Signal <noreply@yourdomain.com>

# Strongly recommended
NEWS_API_KEY=...                  # newsapi.org free key

# App settings
APP_URL=https://yourfrontend.com  # Used in email footer links
DB_PATH=./data/news_tracker.db   # SQLite file path
PORT=8000                         # Set automatically by Render/Fly
```

---

## Extending the App

**Add more keywords** (in `news_fetcher.py`):
```python
AI_KEYWORDS = [
    "your-technology", "your-company", "your-domain",
    ...
]
```

**Change refresh cadence** (in `main.py`):
```python
scheduler.add_job(refresh_news_job, "interval", hours=2)   # Every 2 hours
scheduler.add_job(send_digest_job, "cron", hour=7, minute=30)  # 7:30am UTC
```

**Add a source** (in `news_fetcher.py`): implement an async function returning `List[RawArticle]`, then add it to `fetch_all_news()`.

---

## Tech Stack

```
Backend          Python 3.12 · FastAPI · APScheduler · aiosqlite · aiohttp
AI               Anthropic Claude Haiku (claude-haiku-4-5)
Email            Resend API
Database         SQLite (WAL mode, async via aiosqlite)
News Sources     HN Algolia · arXiv Atom · NewsAPI · Medium RSS (rss2json proxy)
Frontend         React 18 · Vite · No component library (custom editorial CSS)
Typography       Playfair Display · Source Serif 4 · Barlow Condensed
Hosting          Render.com (free) · Fly.io (alt) · Vercel (static)
Containerisation Docker + Docker Compose
IaC              render.yaml + fly.toml included
```
