<div align="center">

# AI SIGNAL

### The Intelligence Briefing for AI & Platform Engineers

*Monitors 10 curated sources every 12 hours · Claude-powered summaries · Competitive intelligence · Daily email digest*

**[Live Demo](https://ai-signal.app) · [Subscribe](https://ai-signal.app) · [API](https://api.ai-signal.app/docs)**

</div>

---

## What It Does

Every morning you open seven tabs, skim thirty headlines, and still feel like you missed something.

AI Signal fixes that. One briefing lands in your inbox at 8 AM UTC — curated from 10 high-signal sources, summarised by Claude, scored for relevance to your stack, and enriched with competitive intelligence on every new tool or model that matters.

**For platform engineers and AI practitioners who need to stay sharp without losing half their morning.**

---

## Features

| Feature | Details |
|---|---|
| **10 Curated Sources** | Medium · PE.org · Anthropic Blog · OpenAI Blog · Google AI Blog · AWS AI Blog · NewsAPI · Stack Overflow Blog · InfoQ · The New Stack |
| **Relevance Scoring** | Claude scores every article 1–10 for AI/platform engineering relevance |
| **Summaries** | 2–3 sentence digest per article — what changed and why it matters |
| **Platform Implication** | One-sentence "For engineers: ..." — always visible, no click needed |
| **Rival Analysis** | Named competitors + specific comparison on every product/model article |
| **Auto-categorisation** | Product/Tool · AI Model · Research Paper · Platform/Infrastructure · Industry News · Tutorial |
| **Daily Digest Email** | Editorial HTML email at 08:00 UTC — clustered stories, sleeper pick, trend detection |
| **Smart Refresh** | Every 12 hours — only NEW articles sent to Claude (skip-duplicates saves ~$0.60/month) |
| **Per-subscriber Threshold** | Each subscriber sets their own min relevance (1–10) |
| **Approval Workflow** | New subscribers require admin approval — one-click Approve/Reject via email |
| **Admin Protection** | All admin endpoints require `?key=` or `X-Admin-Key` header |
| **Newspaper UI** | Two-column React layout — Products left, Research & Models right |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     EVERY 12 HOURS                              │
│                                                                 │
│  news_fetcher.py → quality_score() → get_summarised_ids()       │
│  10 sources          rank top 20       skip already-seen        │
│  async RSS           per-source cap    (zero Claude cost)       │
│       ↓                   ↓                   ↓                 │
│  enrich_all()    → summarize_articles() → upsert_articles()     │
│  trafilatura         Claude Haiku          Turso (libsql)        │
│  full body           summary + category    ON CONFLICT upsert   │
│  extraction          + score + rivals                           │
│                      + implication                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     DAILY 08:00 UTC                             │
│                                                                 │
│  get_top_articles() → curate_digest() → send_daily_digest()     │
│  per subscriber       cluster stories   Resend API              │
│  min_relevance        add implications  HTML email              │
│  filter               sleeper pick      per subscriber          │
│  exclude sent         trend detection                           │
│  articles                                                       │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow detail:**
1. 10 sources fetched concurrently via async RSS — per-source caps prevent flooding
2. Pre-scored by: source bonus + keyword match + recency
3. Top 20 selected (max 3 per source for diversity)
4. Already-summarised articles filtered — Claude only sees new ones
5. trafilatura extracts full article body (falls back to RSS snippet)
6. Claude Haiku returns: summary, category, score, rivals, implication
7. Upserted to Turso — no duplicates ever
8. At 08:00 UTC: editorial digest built and emailed per subscriber
9. Sent article IDs recorded — no article repeated in next 3 days

---

## Tech Stack

```
Backend       Python 3.12 · FastAPI · APScheduler · aiohttp · trafilatura
AI            Claude Haiku 4.5 (claude-haiku-4-5-20251001)
Database      Turso (libSQL cloud SQLite) — persistent, free tier
Email         Resend API (free: 3,000/month)
Frontend      React 18 · Vite · Custom CSS (no component library)
Hosting       Render.com — Pro web service + free static site
Domain        Cloudflare — ai-signal.app (~$10/yr)
```

---

## Cost

| Service | Monthly Cost |
|---|---|
| Claude Haiku API | ~$0.60 |
| Domain (amortised) | ~$0.83 |
| Render free tier | $0 |
| Turso free tier | $0 |
| Resend free tier | $0 |
| **Total** | **~$1.50/month** |

> The skip-duplicates logic means Claude only processes new articles — typically 1–5 per refresh. This keeps API costs at ~$0.60/month regardless of how many subscribers you have.

---

## Deploy

### Prerequisites
- [Render.com](https://render.com) account
- [Turso](https://turso.tech) account (free)
- [Anthropic API key](https://console.anthropic.com)
- [Resend API key](https://resend.com) (free)
- [NewsAPI key](https://newsapi.org) (free)

### Turso Setup

```bash
brew install tursodatabase/tap/turso
turso auth login
turso db create ai-signal
turso db show ai-signal        # copy the URL
turso db tokens create ai-signal  # copy the token
```

### Render Deploy

1. Fork this repo
2. Render → New → Blueprint → connect your fork
3. Set environment variables:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
RESEND_API_KEY=re_...
NEWS_API_KEY=...
ADMIN_API_KEY=your-secret-key      # protects all admin endpoints
ADMIN_EMAIL=you@example.com        # receives subscriber approval emails

# Database
TURSO_URL=libsql://ai-signal-xxx.aws-ap-south-1.turso.io
TURSO_TOKEN=eyJ...
DB_PATH=/tmp/news_tracker.db       # local fallback only

# App
FROM_EMAIL=AI Signal <digest@yourdomain.com>
APP_URL=https://your-frontend.onrender.com
API_URL=https://your-backend.onrender.com
PYTHON_VERSION=3.12.0

# Seed subscribers (optional — Turso persists subscribers automatically)
# Format: Name:email:min_relevance (comma separated)
SEED_SUBSCRIBERS=Alice:alice@example.com:5,Bob:bob@example.com:7

# Model (optional — defaults to claude-haiku)
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

4. Deploy — both services provision automatically via `render.yaml`

---

## Admin Operations

All admin endpoints require `?key=YOUR_ADMIN_API_KEY` or `X-Admin-Key` header.

| Operation | Endpoint |
|---|---|
| Trigger fresh news fetch | `POST /api/trigger-refresh?key=xxx` |
| Send digest to all subscribers | `POST /api/trigger-digest?key=xxx` |
| Send test digest to one email | `POST /api/test-digest?email=you@x.com&key=xxx` |
| Remove retired source articles | `POST /api/clean-sources?key=xxx` |
| Re-run Claude on articles missing rivals | `POST /api/reprocess-rivals?key=xxx` |
| Backfill platform implications | `POST /api/reprocess-implications?key=xxx` |
| Fix implication wording in bulk | `POST /api/fix-implication-wording?key=xxx` |
| Wipe entire articles DB | `POST /api/clear-articles?key=xxx` |
| List all active subscribers | `GET /api/users?key=xxx` |
| List pending approvals | `GET /api/users/pending?key=xxx` |
| Remove a subscriber | `DELETE /api/users/email@x.com?key=xxx` |
| DB breakdown / debug | `GET /api/debug?key=xxx` |

Swagger UI available at: `https://your-api-url/docs`

---

## API Reference (Public)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/news` | Articles — params: `category`, `source`, `min_relevance`, `search`, `limit`, `days` |
| `GET` | `/api/news/stats` | Counts by category |
| `GET` | `/api/news/categories` | Category list |
| `GET` | `/api/news/sources` | Active source list |
| `GET` | `/api/summary` | DB stats + subscriber count |
| `POST` | `/api/users` | Subscribe (triggers admin approval email) |
| `GET` | `/api/users/approve?token=xxx` | Approve subscriber (linked from email) |
| `GET` | `/api/users/reject?token=xxx` | Reject subscriber (linked from email) |
| `GET` | `/api/users/unsubscribe?token=xxx` | Unsubscribe (linked from digest email) |
| `GET` | `/health` | Health check |

---

## Database Schema

```sql
articles (
  id TEXT PRIMARY KEY,          -- URL hash
  title TEXT,
  url TEXT,
  source TEXT,
  author TEXT,
  score INTEGER,                -- pre-Claude quality score
  published_at TEXT,
  summary TEXT,                 -- Claude-generated
  category TEXT,                -- normalised category
  tags TEXT,                    -- JSON array
  relevance_score INTEGER,      -- Claude 1-10
  is_product_or_tool INTEGER,
  product_name TEXT,
  competitors TEXT,             -- JSON array of {name, description, comparison}
  competitive_advantage TEXT,
  platform_implication TEXT,    -- "For engineers: ..." one-liner
  fetched_at TEXT
)

users (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE,
  name TEXT,
  active INTEGER DEFAULT 0,     -- 0 = pending approval
  min_relevance INTEGER DEFAULT 5,
  categories TEXT,              -- JSON array filter
  approval_token TEXT,
  unsubscribe_token TEXT
)

digest_sent_articles (
  recipient_email TEXT,
  article_id TEXT,
  sent_at TEXT,
  UNIQUE(recipient_email, article_id)
  -- auto-cleaned after 7 days
)

kv_store (
  key TEXT PRIMARY KEY,
  value TEXT
  -- stores digest_sent_date for missed-digest detection
)

digest_log (
  id INTEGER,
  sent_at TEXT,
  recipient_email TEXT,
  article_count INTEGER,
  status TEXT
)
```

---

## Project Structure

```
ai-news-tracker/
├── backend/
│   ├── main.py                 # FastAPI app, scheduler, admin endpoints
│   ├── database.py             # Turso/libsql, all DB queries
│   ├── news_fetcher.py         # 10 sources, RSS fetching, quality scoring
│   ├── summarizer.py           # Claude Haiku integration
│   ├── digest_curator.py       # Editorial digest: clustering, implications, sleeper
│   ├── emailer.py              # HTML email building, Resend API
│   ├── requirements.txt
│   └── routers/
│       ├── news.py             # GET /api/news endpoints
│       ├── users.py            # Subscriber management
│       └── config.py           # Source/config endpoints
├── frontend/
│   └── src/
│       └── App.jsx             # React app — full UI
├── render.yaml                 # One-click Render Blueprint deploy
└── README.md
```

---

## Digest Email Format

The daily digest is editorial, not algorithmic:

- **Story clustering** — same story from 4 sources → one entry with "also covered by"
- **Adaptive count** — 10–14 stories based on quality that day
- **Sleeper pick** — one under-the-radar article from a less mainstream source
- **Noise filter** — funding rounds with no product, thin summaries, auto-excluded
- **Trend detection** — recurring themes surfaced: "AI agents in CI/CD — 6 articles this week"
- **No repeats** — sent article IDs tracked per subscriber; same article won't appear for 3 days
- **Personalised** — each subscriber's min relevance threshold applied before selection

Subject format: `AI Signal · Jun 10, 2026 · 12 stories`

---

## Sources

| Source | Type | Cap |
|---|---|---|
| Anthropic Blog | Company blog | 20 |
| OpenAI Blog | Company blog | 20 |
| Google AI Blog | Company blog | 20 |
| AWS AI Blog | Company blog | 15 |
| platformengineering.org | Community | 20 |
| Medium (AI/MLOps tags) | Community | 8 |
| Stack Overflow Blog | Community | 10 |
| InfoQ | Industry | 10 |
| The New Stack | Industry | 10 |
| NewsAPI | Aggregator | 15 |

Sources go through `is_relevant()` keyword filter — company blogs bypass this (ALWAYS_RELEVANT). Platform engineering terms (kubernetes, k8s, gitops, observability, backstage) are included in keywords so platform content passes even without AI keywords.

---

## Keep-Alive Cron (Free Tier)

Render free tier spins down after 15 minutes of inactivity. Add a keep-alive ping to prevent cold starts and missed digests.

1. Go to [cron-job.org](https://cron-job.org) — free, no card needed
2. Create job: `GET https://api.ai-signal.app/health` — every 10 minutes
3. Optionally add a second job: `POST https://api.ai-signal.app/api/trigger-digest` with `X-Admin-Key` header — at 8:05 AM UTC daily (more reliable than APScheduler on free tier)

---

## Known Limitations

- **Render Pro required for reliable digest** — free tier random restarts can cause missed 8 AM digest
- **NewsAPI free tier** — 100 requests/day, developer plan only (no production use)
- **trafilatura extraction** — paywalled articles get thin content; Claude does its best
- **Rivals only on product articles** — articles categorised as Industry News or Tutorial won't have rival analysis even if they mention products

---

## License

MIT
