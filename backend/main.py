"""
AI News Tracker - FastAPI Backend
"""

import os
import asyncio
import aiohttp
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, get_db
from news_fetcher import fetch_all_news
from summarizer import summarize_articles, enrich_all
from news_fetcher import quality_score
from emailer import send_daily_digest
from digest_curator import curate_digest
from routers import news, users, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def keep_alive_ping():
    """Ping own /health endpoint every 10 min to prevent Render free tier spin-down."""
    api_url = os.getenv("API_URL", "")
    if not api_url:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                logger.debug(f"Keep-alive ping: {r.status}")
    except Exception as e:
        logger.debug(f"Keep-alive ping failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler.add_job(refresh_news_job, "interval", hours=12,
                      id="refresh_news", replace_existing=True,
                      misfire_grace_time=300)   # run even if missed by up to 5 min
    scheduler.add_job(send_digest_job, "cron", hour=8, minute=0,
                      timezone="UTC", id="daily_digest", replace_existing=True,
                      misfire_grace_time=300)   # critical — server restart at 8AM would skip digest
    # Keep-alive ping — prevents Render free tier from spinning down
    # Pings /health every 10 minutes so the server stays warm for the 8 AM digest
    scheduler.add_job(keep_alive_ping, "interval", minutes=10,
                      id="keep_alive", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")

    # Seed subscribers from env — survives ephemeral restarts
    # Format: "Alice:alice@example.com,Bob:bob@example.com"
    seed = os.getenv("SEED_SUBSCRIBERS", "").strip()
    if seed:
        async with get_db() as db:
            for entry in seed.split(","):
                entry = entry.strip()
                if ":" in entry:
                    # Format: "Name:email" or "Name:email:min_relevance"
                    parts = entry.split(":", 2)
                    name  = parts[0].strip()
                    email = parts[1].strip()
                    min_relevance = int(parts[2].strip()) if len(parts) > 2 else 5
                    await db.create_user(
                        email=email, name=name,
                        min_relevance=min_relevance,
                        require_approval=False,  # seed users bypass approval
                    )
                    logger.info(f"Seeded subscriber: {email} (min_relevance={min_relevance})")

    asyncio.create_task(refresh_news_job())
    yield
    scheduler.shutdown()


app = FastAPI(
    title="AI News Tracker",
    description="AI/ML news with summaries, competitor analysis and daily digests",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Admin auth ────────────────────────────────────────────────────────────────
async def require_admin(x_admin_key: str = Header(default="")):
    """Validates X-Admin-Key header against ADMIN_API_KEY env var."""
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        logger.warning("ADMIN_API_KEY not set — admin endpoints are unprotected!")
        return
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(news.router,   prefix="/api/news",   tags=["news"])
app.include_router(users.router,  prefix="/api/users",  tags=["users"])
app.include_router(config.router, prefix="/api/config", tags=["config"])


async def refresh_news_job():
    logger.info("News refresh starting...")
    try:
        # Step 1 — fetch from all sources
        raw_articles = await fetch_all_news()
        logger.info(f"Fetched {len(raw_articles)} raw articles")

        # Step 2 — score ALL articles FIRST, then pick top 20
        # CRITICAL: scoring must happen before filtering already-seen articles.
        # If we filter first, only Medium (always fresh) survives and dominates.
        raw_articles.sort(key=quality_score, reverse=True)

        # Pick top 20 with max 5 per source — prevents any single source from flooding all 20 slots
        top_articles, source_dist = [], {}
        for a in raw_articles:
            if len(top_articles) >= 20:
                break
            if source_dist.get(a.source, 0) < 5:
                top_articles.append(a)
                source_dist[a.source] = source_dist.get(a.source, 0) + 1
        logger.info(f"Top 20 by quality score: {source_dist}")

        # Step 3 — from the top 20, find which ones Claude hasn't seen yet
        async with get_db() as db:
            already_seen = await db.get_summarised_ids()

        new_articles = [a for a in top_articles if a.id not in already_seen]
        logger.info(
            f"Top 20: {len(top_articles)} total, "
            f"{len(already_seen & {a.id for a in top_articles})} already in DB, "
            f"{len(new_articles)} need Claude"
        )

        if not new_articles:
            logger.info("All top 20 already summarised — refresh complete")
            return

        # Step 4 — enrich + Claude only for new ones
        new_articles = await enrich_all(new_articles)
        processed = await summarize_articles(new_articles)
        logger.info(f"Summarised {len(processed)} new articles")

        if processed:
            async with get_db() as db:
                await db.upsert_articles(processed)
            logger.info("Refresh complete")

    except Exception as e:
        logger.error(f"News refresh failed: {e}", exc_info=True)


async def send_digest_job():
    logger.info("Sending daily digest...")
    try:
        async with get_db() as db:
            active_users = await db.get_active_users()

        async def send_one(user):
            try:
                # Step 1 — fetch candidate articles for this subscriber
                async with get_db() as db:
                    candidates = await db.get_top_articles(
                        limit=20,
                        min_relevance=user.min_relevance or 5,
                        categories=user.categories or None,
                        hours=24,
                    )

                if not candidates:
                    # Widen to 7 days if nothing in last 24h
                    async with get_db() as db:
                        candidates = await db.get_top_articles(limit=30, min_relevance=5, hours=168)

                if not candidates:
                    logger.info(f"No articles for {user.email} — skipping")
                    return

                # Step 2 — run editorial curator
                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with get_db() as db:
                        digest = await curate_digest(candidates, db, session)

                logger.info(
                    f"Digest for {user.email}: {digest['article_count']} articles "
                    f"({len(digest['stories'])} stories, sleeper={digest['sleeper'] is not None})"
                )

                # Step 3 — send
                success = await send_daily_digest(user, digest)
                if success:
                    logger.info(f"Digest sent to {user.email}")
                else:
                    logger.error(f"Digest FAILED for {user.email}")
            except Exception as e:
                logger.error(f"Digest error for {user.email}: {e}", exc_info=True)

        for i, user in enumerate(active_users):
            await send_one(user)
            if i < len(active_users) - 1:
                await asyncio.sleep(1)
        logger.info(f"Digest complete — {len(active_users)} users")
    except Exception as e:
        logger.error(f"Digest failed: {e}", exc_info=True)


@app.get("/")
async def root():
    return {"status": "online", "service": "AI News Tracker"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/debug")
async def debug(_=Depends(require_admin)):
    """Shows exactly what the UI displays and why."""
    async with get_db() as db:
        # Total in DB by source
        by_source = await db._query(
            "SELECT source, COUNT(*) as total, "
            "MIN(substr(published_at,1,10)) as oldest, "
            "MAX(substr(published_at,1,10)) as newest "
            "FROM articles GROUP BY source ORDER BY total DESC"
        )
        # What passes the 30-day date filter
        passing_filter = await db._query(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE MAX(COALESCE(substr(published_at,1,10),'1970-01-01'), "
            "         COALESCE(substr(fetched_at,1,10),'1970-01-01')) "
            ">= date('now','-30 days') "
            "GROUP BY source ORDER BY n DESC"
        )
        # Exactly what UI shows (same query as get_articles)
        ui_articles = await db.get_articles(limit=40, days=30)
        ui_sources = {}
        for a in ui_articles:
            ui_sources[a["source"]] = ui_sources.get(a["source"], 0) + 1
        # Sample old articles if any
        old_articles = await db._query(
            "SELECT source, substr(published_at,1,10) as pub_date, "
            "relevance_score, substr(title,1,60) as title "
            "FROM articles "
            "WHERE substr(published_at,1,10) < date('now','-30 days') "
            "ORDER BY relevance_score DESC LIMIT 10"
        )

    return {
        "db_by_source":       {r["source"]: {"total": r["total"], "oldest": r["oldest"], "newest": r["newest"]} for r in by_source},
        "passing_30day_filter": {r["source"]: r["n"] for r in passing_filter},
        "ui_shows":           ui_sources,
        "ui_total":           len(ui_articles),
        "old_articles_in_db": [dict(r) for r in old_articles],
    }


@app.post("/api/clear-articles")
async def clear_articles(_=Depends(require_admin)):
    """Delete all articles — use when DB has stale/corrupt data."""
    async with get_db() as db:
        await db._exec("DELETE FROM articles")
    return {"message": "All articles deleted — trigger a refresh to repopulate"}


@app.post("/api/clean-sources")
async def clean_sources(_=Depends(require_admin)):
    """Remove articles from all retired sources from the DB."""
    removed_sources = [
        "arXiv", "MIT AI News", "Google DeepMind", "Google Research",
    ]
    async with get_db() as db:
        await db._exec("DELETE FROM articles WHERE source LIKE 'NewsAPI / %'")
        for src in removed_sources:
            await db._exec("DELETE FROM articles WHERE source = ?", (src,))
        rows = await db._query("SELECT COUNT(*) as n FROM articles")
        remaining = rows[0]["n"] if rows else 0
    return {"message": f"Cleaned retired sources. {remaining} articles remain."}


@app.get("/api/summary")
async def get_summary():
    """Combined stats + config — reduces page load from 4 API calls to 2."""
    async with get_db() as db:
        s = await db.get_stats()
    return {
        "total_articles":       s["total_articles"],
        "product_articles":     s["product_articles"],
        "by_category":          s["by_category"],
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "resend_configured":    bool(os.getenv("RESEND_API_KEY")),
        "news_api_configured":  bool(os.getenv("NEWS_API_KEY")),
        "turso_configured":     bool(os.getenv("TURSO_URL")),
        "refresh_interval_hours": 12,
        "digest_time_utc":      "08:00",
        "sources": [
            "Medium", "platformengineering.org",
            "Anthropic Blog", "OpenAI Blog", "Google AI Blog", "AWS AI Blog", "NewsAPI",
        ],
    }



@app.post("/api/reprocess-rivals")
async def reprocess_rivals(_=Depends(require_admin)):
    """Force re-analyse all product/tool articles that have no competitor data."""
    try:
        async with get_db() as db:
            async with db._db.execute(
                """SELECT id FROM articles
                   WHERE is_product_or_tool = 1
                   AND (competitors IS NULL OR competitors = '[]' OR competitors = '')
                   AND summary IS NOT NULL AND LENGTH(summary) > 40"""
            ) as cur:
                rows = await cur.fetchall()
            ids_to_reset = [r["id"] for r in rows]

            if ids_to_reset:
                placeholders = ",".join("?" * len(ids_to_reset))
                await db._db.execute(
                    f"UPDATE articles SET summary = '' WHERE id IN ({placeholders})",
                    ids_to_reset
                )
                await db._db.commit()

        logger.info(f"Flagged {len(ids_to_reset)} product articles for re-analysis")
        return {"message": f"Flagged {len(ids_to_reset)} articles — trigger a refresh to re-analyse them"}
    except Exception as e:
        logger.error(f"Reprocess rivals failed: {e}")
        return {"error": str(e)}

@app.post("/api/trigger-refresh")
async def trigger_refresh(background_tasks: BackgroundTasks, _=Depends(require_admin)):
    background_tasks.add_task(refresh_news_job)
    return {"message": "News refresh triggered"}


@app.post("/api/trigger-digest")
async def trigger_digest(background_tasks: BackgroundTasks, _=Depends(require_admin)):
    background_tasks.add_task(send_digest_job)
    return {"message": "Digest triggered for all subscribers"}


@app.post("/api/test-digest")
async def test_digest(email: str, _=Depends(require_admin)):
    """
    Send a test digest to ONE email only — does not send to other subscribers.
    Uses that subscriber's settings if they exist, otherwise uses defaults.
    Call via Swagger or: POST /api/test-digest?email=you@example.com
    """
    async with get_db() as db:
        user = await db.get_user_by_email(email)

    if not user:
        class MockUser:
            def __init__(self, e):
                self.email             = e
                self.name              = e.split("@")[0].title()
                self.min_relevance     = 5
                self.categories        = None
                self.unsubscribe_token = ""
        user = MockUser(email)
        logger.info(f"Test digest: no subscriber for {email} — using defaults")
    else:
        logger.info(f"Test digest to {email} (min_relevance={user.min_relevance})")

    # Fetch candidates — try 24h first, fallback to 7 days
    async with get_db() as db:
        candidates = await db.get_top_articles(limit=30, min_relevance=user.min_relevance or 5,
                                                categories=getattr(user,"categories",None), hours=24)
    if not candidates:
        async with get_db() as db:
            candidates = await db.get_top_articles(limit=30, min_relevance=5, hours=168)
    if not candidates:
        return {"error": "No articles in DB — run a refresh first"}

    # Curate and send
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with get_db() as db:
            digest = await curate_digest(candidates, db, session)

    success = await send_daily_digest(user, digest)
    return {
        "sent":          success,
        "to":            email,
        "stories":       len(digest.get("stories", [])),
        "has_sleeper":   digest.get("sleeper") is not None,
        "trends":        digest.get("trends", []),
        "article_count": digest.get("article_count", 0),
    }
