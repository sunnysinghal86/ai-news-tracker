<div align="center">

# AI SIGNAL

### The Intelligence Briefing for AI Engineers

*Tracks AI/ML news across 10 curated sources — Medium · PE.org · Anthropic · OpenAI · Google AI · AWS · NewsAPI · Stack Overflow · InfoQ · The New Stack*  
*Claude-powered summaries · Competitor analysis · Daily email digest*

---

**[Live Demo](#deployment) · [API Docs](#api-reference) · [Deploy in 10 min](#quick-deploy)**

</div>

---

## The Pitch

> **Every morning you open seven tabs, skim thirty headlines, and still feel like you missed something.**

AI Signal fixes that. One beautifully designed briefing lands in your inbox at 8 AM — curated from 10 high-signal sources engineers actually read, summarised by Claude, scored for relevance to *your* stack, and enriched with competitive intelligence on every new tool or model that matters.

It's not a newsletter you subscribed to and forgot. It's infrastructure you own.

**For platform engineers and software developers who need to stay sharp without losing half their morning to tab management.**

---

## Who Is This For?

| Persona | Problem Solved |
|---|---|
| **Platform / DevX Engineer** | Knows instantly which new AI tool threatens or enhances their current stack |
| **Engineering Manager** | Morning brief before standup — no research required |
| **ML Ops / AI Infra** | Company blog releases + production tool releases in one feed, relevance-ranked |
| **Tech Lead** | Competitor analysis for every product launch: are we behind? |
| **Independent Dev / Hacker** | Runs on ~$1/month with zero managed infrastructure |

---

## Feature Overview

| Feature | Details |
|---|---|
| **10 Sources** | Medium, PE.org, Anthropic Blog, OpenAI Blog, Google AI Blog, AWS AI Blog, NewsAPI, Stack Overflow Blog, InfoQ, The New Stack |
| **Claude Haiku Summaries** | 2–3 sentence digest per article — powered by full article body extraction via trafilatura |
| **Competitor Analysis** | For every product/tool/model: lists rivals + *how this one differs* |
| **Relevance Scoring** | 1–10 score weighted toward Software Dev & Platform Engineering |
| **Auto Categorisation** | Product/Tool · AI Model · Research · News · Tutorial · Platform/Infra |
| **Smart Refresh** | Fetches every 12 hours — only NEW articles sent to Claude (already-summarised ones skipped) |
| **Keep-Alive Cron** | cron-job.org pings `/health` every 10 minutes to prevent Render spin-down |
| **Daily Digest Email** | One HTML email per day at 08:00 UTC via Resend |
| **Editorial Dashboard** | Newspaper-style React UI — collapsible summaries, rival analysis, filters |
| **Multi-subscriber** | Up to 75 users, each with personal preferences and relevance thresholds |
| **Approval Workflow** | New subscribers require admin approval via one-click email — Approve or Reject buttons |

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
       │  │ NewsAPI      │ │  Medium RSS  │ │  platformeng      │ │  Company Blogs   │  │
       │  │ (reputable   │ │  (via rss2   │ │  .org RSS         │ │  Anthropic/OpenAI│  │
       │  │  domains)    │ │   json)      │ │  (free)           │ │  Google AI/AWS   │  │
       │  └──────────────┘ └──────────────┘ └──────────────────┘ └──────────────────┘  │
       │                                                │                                │
       │  ┌──────────────┐ ┌──────────────┐ ┌──────────┴───────────────────────────┐   │
       │  │ platform     │ │              │ │          Claude API                  │   │
       │  │ engineering  │ │              │ │     (Anthropic — claude-haiku)       │   │
       │  │ .org RSS     │ │              │ │  Summarise + Categorise + Rivals     │   │
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
                                            │  (up to 75 users)    │
                                            └──────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                              DATA LAYER                                      │
 │                                                                              │
 │   Turso (libSQL cloud) · persistent across restarts · free tier               │
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

DATA FLOW SEQUENCE (every 12 hours)
════════════════════════════════
  1. APScheduler triggers fetch_all_news() every 12 hours (2×/day)
  2. 6 async tasks launched concurrently (HN + arXiv + NewsAPI + Medium + PE.org + PW)
  3. Raw articles deduplicated by URL hash
  4. Already-summarised articles filtered out — zero Claude cost for known articles
  5. Content enrichment: trafilatura extracts full article body for NEW articles (falls back to og:description for paywalled sites)
  6. New articles (typically 10–20 per refresh) sent to Claude Haiku with up to 1,200 chars of real content
  7. Results upserted to Turso via libSQL (ON CONFLICT — no duplicates)
  8. At 08:00 UTC: top articles pulled, HTML email built per subscriber
  9. Resend API delivers personalised digest to each inbox
  10. digest_log entry written for audit trail
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
#    FROM_EMAIL=AI Signal <digest@ai-signal.app>
#    SEED_SUBSCRIBERS=YourName:you@email.com:5
#    PYTHON_VERSION=3.12.0

# 4. Click Deploy. Both services go live with public HTTPS URLs.
```

Your app will be live at:
- **Frontend**: `https://ai-signal.app`
- **Backend API**: `https://api.ai-signal.app`
- **API Docs**: `https://api.ai-signal.app/docs`

---

## Database Setup (Turso)

AI Signal uses [Turso](https://turso.tech) — a free cloud SQLite service — to persist articles and subscribers across Render restarts. Without it, your data is wiped every time the service redeploys.

**Why Turso:**
- Free tier: 500 databases, 9GB storage, 1 billion row reads/month
- Zero ops — no managed DB, no Redis, no message queue
- Mumbai region (`aws-ap-south-1`) — lowest latency for India-based deployments

**Setup (5 minutes):**

```bash
# 1. Install Turso CLI
brew install tursodatabase/tap/turso

# 2. Login
turso auth login

# 3. Create database
turso db create ai-signal

# 4. Get URL
turso db show ai-signal

# 5. Create auth token
turso db tokens create ai-signal
```

Then add to Render → backend → Environment:
```
TURSO_URL   = libsql://ai-signal-<your-id>.aws-ap-south-1.turso.io
TURSO_TOKEN = eyJ...
```

The app falls back to local SQLite (`DB_PATH`) if `TURSO_URL` is not set — useful for local development.

---

## Keep-Alive Cron (Required for Free Tier)

Render's free tier spins down web services after 15 minutes of inactivity, causing a cold-start delay on the next request. A keep-alive cron job prevents this.

**Setup (already configured for this deployment):**

1. Go to **[cron-job.org](https://cron-job.org)** — free account, no card
2. Create a new cron job:
   - **URL**: `https://api.ai-signal.app/health`
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
| `GET` | `/api/users/approve?token=xxx` | Approve pending subscriber (linked from email) |
| `GET` | `/api/users/reject?token=xxx` | Reject and delete pending subscriber (linked from email) |
| `GET` | `/api/users/pending` | List subscribers awaiting approval |
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
| Resend (email) | 3,000 emails/month | ~90 (3 users) → ~2,250 (75 users) | **$0** |
| NewsAPI | 100 req/day | ~6 req/day | **$0** |
| arXiv API | Unlimited | — | **$0** |
| platformengineering.org RSS | Unlimited | — | **$0** |
| Anthropic Blog RSS | Unlimited | — | **$0** |
| OpenAI Blog RSS | Unlimited | — | **$0** |
| Google DeepMind RSS | Unlimited | — | **$0** |
| Google Research RSS | Unlimited | — | **$0** |
| AWS AI Blog RSS | Unlimited | — | **$0** |
| Google AI Blog RSS | Unlimited | — | **$0** |
| MIT AI News RSS | Unlimited | — | **$0** |
| Turso (cloud SQLite) | Free tier | 9GB storage | **$0** |
| cron-job.org | Free | 4,320 pings/month | **$0** |
| Claude Haiku 4.5 | $1.00/1M input, $5.00/1M output | ~28–30 new articles/day (cap enforced) | **~$2.50/month** |
| **TOTAL** | | | **~$2.50/month** |

---

## Configuration Reference

```bash
# Render Environment Variables

# Required
ANTHROPIC_API_KEY=sk-ant-...          # Claude Haiku for AI analysis
RESEND_API_KEY=re_...                  # Email delivery (resend.com)
FROM_EMAIL=AI Signal <digest@ai-signal.app>
PYTHON_VERSION=3.12.0                  # Pin Python — avoids build failures

# Database (Turso cloud SQLite — persists data across restarts)
TURSO_URL=libsql://ai-signal-xxx.turso.io   # from: turso db show ai-signal
TURSO_TOKEN=eyJ...                           # from: turso db tokens create ai-signal

# Strongly recommended
NEWS_API_KEY=...                       # newsapi.org free key (100 req/day)

# Admin approval
ADMIN_EMAIL=sunnysinghal86@gmail.com    # receives approval emails for new subscribers

# Subscriber seeding — safety net (Turso persists subscribers automatically)
# Format: "Name1:email1@x.com,Name2:email2@x.com"
SEED_SUBSCRIBERS=Alice:alice@example.com,Bob:bob@example.com:7  # optional :min_relevance suffix

# App settings
APP_URL=https://ai-signal.app
TURSO_URL=libsql://ai-signal-xxx.aws-ap-south-1.turso.io  # from: turso db show ai-signal
TURSO_TOKEN=eyJ...                        # from: turso db tokens create ai-signal
DB_PATH=/tmp/news_tracker.db              # local dev fallback only — ignored when TURSO_URL is set
```

---

## Extending the App

**Add keywords** (`news_fetcher.py`):
```python
AI_KEYWORDS = ["your-technology", "your-company", ...]
```

**Change refresh cadence** (`main.py`):
```python
scheduler.add_job(refresh_news_job, "interval", hours=12)  # default — 2×/day, ~$1.70/month
scheduler.add_job(send_digest_job, "cron", hour=7, minute=30)  # digest at 7:30am UTC
```

> ⚠️ Do not set refresh below 2 hours — Claude Haiku has a 10,000 output token/minute rate limit. Already-summarised articles are skipped automatically so cost stays low regardless of frequency.

**Add a source** (`news_fetcher.py`): implement an async function returning `List[RawArticle]`, add it to the `gather()` call in `fetch_all_news()`.

---

## Testing

The backend has a full unit and integration test suite covering all modules.

### Setup

```bash
# Requires Python 3.12 (not 3.13/3.14 — pydantic-core build constraint)
python3.12 --version   # verify

# Create a dedicated virtualenv
cd backend
python3.12 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install all dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### Run Tests

```bash
# All tests
pytest

# With verbose output
pytest -v

# Single file
pytest tests/test_database.py -v

# Single test class
pytest tests/test_database.py::TestGetTopArticles -v

# Single test
pytest tests/test_summarizer.py::TestCallClaude::test_retries_on_429_then_returns_none -v

# Stop on first failure
pytest -x
```

### Test Coverage — 72 test cases across 5 modules

#### `tests/test_news_fetcher.py` — 21 tests
| Class | What's covered |
|---|---|
| `TestGenId` | Same URL → same ID, different URLs → different IDs, always 12 chars, alphanumeric, stable on empty string |
| `TestStripHtml` | Removes tags, nested tags, decodes `&amp;`/`&nbsp;`, collapses whitespace, strips `<script>` and `<style>` blocks |
| `TestRawArticle` | Default content/score/tags are correct, all fields stored accurately |
| `TestFetchHackerNews` | Returns empty list on HTTP 500, returns empty list on network exception |
| `TestFetchArxiv` | Returns empty list on HTTP 503, returns empty list on network exception |
| `TestDeduplication` | Duplicate IDs removed, all unique articles returned, failed source doesn't crash `fetch_all_news` |

#### `tests/test_database.py` — 22 tests
| Class | What's covered |
|---|---|
| `TestUpsertArticles` | Inserts new, updates existing on conflict, inserts multiple, competitors serialised as JSON, empty list is no-op |
| `TestGetSumarisedIds` | Includes fully processed, excludes empty/short summary, **excludes product with no competitors** (re-queue spec), includes product with competitors |
| `TestGetTopArticles` | Filters by `min_relevance`, ordered by score desc, filters by category, excludes no-summary articles, respects limit, fallback time window (24h→48h→7d) |
| `TestGetArticles` | No filters, filter by source, filter by `min_relevance`, title search, pagination no overlap |
| `TestUserManagement` | Create and retrieve user, `min_relevance` stored, categories stored, duplicate email no crash |
| `TestGetStats` | Total count accurate, product count accurate, empty DB returns zero |

#### `tests/test_summarizer.py` — 14 tests
| Class | What's covered |
|---|---|
| `TestCallClaude` | Returns text on 200, returns None with no API key, retries on 429 then returns None, returns None on 5xx |
| `TestAnalyseArticle` | Parses valid JSON fully, defaults on malformed JSON, returns `ProcessedArticle` on None response, missing fields use defaults |
| `TestEnrichOne` | Skips rich content (>200 chars), skips HN URLs, skips 5 paywalled domains, uses trafilatura when available, og:description regex correct, handles HTTP 404, handles network exception |
| `TestSummarizeArticles` | Caps at 30 articles when API key set, no-key returns content fallback for all, **content cap is 1200 chars** (not old 600) |

#### `tests/test_emailer.py` — 14 tests
| Class | What's covered |
|---|---|
| `TestSendEmail` | Returns False with no key, **reads API key fresh at call time** (not cached at import), returns False on 401, returns False on network exception |
| `TestSendDailyDigest` | Returns False for empty articles, subject includes correct article count, sends to correct email address, returns True on success, returns False on send failure |
| `TestBuildHtmlEmail` | Includes subscriber name, includes article title, includes article summary, renders without competitors, renders multiple articles, returns a string |

#### `tests/test_api.py` — 15 integration tests
| Class | Endpoints covered |
|---|---|
| `TestHealthEndpoints` | `GET /` returns 200, `GET /health` returns `{"status":"healthy"}` |
| `TestGetNews` | Returns articles + count, empty DB returns `[]`, filter by category, filter by `min_relevance`, search, limit enforced, max limit 100, pagination no overlap |
| `TestStats` | `GET /api/news/stats` returns `total_articles`, empty DB returns 0 |
| `TestMeta` | Categories list contains known values, sources list non-empty |
| `TestSubscribe` | `POST /api/users` creates subscriber, duplicate email no 500, response contains user object |
| `TestTriggerEndpoints` | `POST /api/trigger-refresh` returns 200, `POST /api/trigger-digest` returns 200 |
| `TestReprocessRivals` | `POST /api/reprocess-rivals` returns 0 on empty DB, handles seeded data correctly |

### Key Business Logic Specs

These tests directly encode critical product behaviours:

- **Re-queue spec** (`TestGetSumarisedIds::test_excludes_product_with_no_competitors`) — product articles with empty competitors are excluded from the "already done" set, forcing Claude to re-analyse them on next refresh
- **1200 char content window** (`TestSummarizeArticles::test_content_cap_is_1200_chars_in_prompt`) — verifies trafilatura upgrade was reflected in the Claude prompt (old cap was 600)
- **API key freshness** (`TestSendEmail::test_reads_api_key_fresh_not_cached`) — Resend key must be read from env at call time, not cached at module import
- **Digest time-window fallback** (`TestGetTopArticles::test_fallback_expands_time_window`) — if fewer than 5 articles in 24h window, query expands to 48h then 7 days before falling back to best available

---

## How It All Connects

```
┌─────────────────────────────────────────────────────────────────────┐
│                     EVERY 12 HOURS                                  │
│                                                                     │
│  news_fetcher.py          summarizer.py          database.py        │
│  ─────────────────        ─────────────          ───────────        │
│  Fetch 10 sources   →     quality_score()   →    get_summarised     │
│  concurrently             rank articles          _ids()             │
│  (asyncio.gather)                                                   │
│                           cap at 20              skip already-      │
│                           (top by score)         seen articles      │
│                                                                     │
│                           enrich_all()           upsert_articles()  │
│                           (trafilatura +          ON CONFLICT —      │
│                            og:description)        never duplicates  │
│                                                                     │
│                           Claude Haiku            normalise         │
│                           summary + category      category values   │
│                           + rivals + score                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     EVERY DAY 08:00 UTC                             │
│                                                                     │
│  database.py              emailer.py             Resend API         │
│  ─────────────            ──────────             ──────────         │
│  get_top_articles()  →    curate_digest()  →    build HTML email    │
│  per subscriber           cluster stories       deliver to inbox    │
│  (min_relevance +         add implications      via Resend API      │
│   category filter)        detect trends                             │
│                                                                     │
│  fallback cascade:        sent sequentially      1s gap between     │
│  24h → 48h → 7d →         (not concurrent)       users avoids       │
│  best available                                  rate limit         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     USER VISITS ai-signal.app                       │
│                                                                     │
│  App.jsx (React)          FastAPI                database.py        │
│  ─────────────            ───────                ───────────        │
│  useApi() hooks     →     GET /api/news     →    get_articles()     │
│  fetch on mount           GET /api/stats         SQL with filters   │
│  re-fetch on filter       GET /api/config                           │
│  change                   GET /api/users                            │
│                                                                     │
│  Split articles:          JSON response     →    articles returned  │
│  PLATFORM_CATS → left                                               │
│  RESEARCH_CATS → right                                              │
│  uncategorised → left                                               │
│                                                                     │
│  leadScore() picks                                                  │
│  best article from                                                  │
│  top 10 as headline                                                 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     NEW SUBSCRIBER FLOW                             │
│                                                                     │
│  App.jsx              database.py          emailer.py               │
│  ─────────            ───────────          ──────────               │
│  Subscribe form  →    create_user()   →    send_approval_request()  │
│  POST /api/users      active=0             to ADMIN_EMAIL           │
│                       approval_token       with ✅ Approve          │
│                       = random 32 chars    and ❌ Reject buttons    │
│                                                ↓                   │
│                       approve_user()  ←    Admin clicks Approve     │
│                       active=1                                      │
│                       token cleared    →    send welcome email      │
│                                             to subscriber           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

```
Backend          Python 3.12 · FastAPI · APScheduler · libsql · aiohttp · trafilatura
AI               Anthropic Claude Haiku (claude-haiku-4-5-20251001)
Email            Resend API (free tier: 3,000/month)
Database         Turso (libSQL cloud SQLite) — persistent, survives restarts, free tier
News Sources     Medium · platformengineering.org · Anthropic Blog · OpenAI Blog
                 Google AI Blog · AWS AI Blog · NewsAPI
                 Stack Overflow Blog · InfoQ · The New Stack
Article Extract  trafilatura (full body) → og:description fallback → raw RSS snippet
Frontend         React 18 · Vite · Custom editorial CSS (no component library)
Typography       Playfair Display · Source Serif 4 · Barlow Condensed
Hosting          Render.com — backend (free web service) + frontend (free static site)
Keep-Alive       cron-job.org — pings /health every 10 min to prevent spin-down
IaC              render.yaml included for one-click Blueprint deploy
```
