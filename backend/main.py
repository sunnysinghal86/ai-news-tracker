"""
AI News Tracker - FastAPI Backend
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, get_db
from news_fetcher import fetch_all_news
from summarizer import summarize_articles, enrich_all
from news_fetcher import quality_score
from emailer import send_daily_digest
from routers import news, users, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler.add_job(refresh_news_job, "interval", hours=12,  # every 12h — ~$1.70/month
                      id="refresh_news", replace_existing=True)
    scheduler.add_job(send_digest_job, "cron", hour=8, minute=0,
                      id="daily_digest", replace_existing=True)
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
        # Step 1 — fetch from all 14 sources
        raw_articles = await fetch_all_news()
        logger.info(f"Fetched {len(raw_articles)} raw articles from all sources")

        # Step 2 — get IDs already summarised in DB (skip these to save Claude cost)
        async with get_db() as db:
            already_seen = await db.get_summarised_ids()
        logger.info(f"Skipping {len(already_seen)} already-summarised articles")

        # Step 3 — filter to only new/unseen articles
        new_articles = [a for a in raw_articles if a.id not in already_seen]
        logger.info(f"New articles to process: {len(new_articles)}")

        if not new_articles:
            logger.info("No new articles — refresh complete")
            return

        # Step 4 — cap BEFORE enriching using quality score
        # quality_score combines: source authority + HN score + keyword strength + recency
        # arXiv (weight=8) and MIT AI News (weight=7) naturally rank above Medium (5)
        # and PE.org (4) so no manual slot reservation is needed
        cap = 20
        if len(new_articles) > cap:
            new_articles.sort(key=quality_score, reverse=True)
            new_articles = new_articles[:cap]
            logger.info(f"Capped to top {cap} articles by quality score")

        # Step 5 — enrich content only for capped set (trafilatura, no API cost)
        new_articles = await enrich_all(new_articles)
        logger.info(f"Enrichment done for {len(new_articles)} articles")

        # Step 6 — send to Claude
        processed = await summarize_articles(new_articles)
        logger.info(f"Summarised {len(processed)} articles")

        # Step 7 — upsert into DB
        if processed:
            async with get_db() as db:
                await db.upsert_articles(processed)
            logger.info(f"Stored {len(processed)} articles — refresh complete")

    except Exception as e:
        logger.error(f"News refresh failed: {e}", exc_info=True)


async def send_digest_job():
    logger.info("Sending daily digest...")
    try:
        async with get_db() as db:
            active_users = await db.get_active_users()

        # Each user gets their own filtered article list
        async def send_one(user):
            async with get_db() as db:
                articles = await db.get_top_articles(
                    limit=10,
                    min_relevance=user.min_relevance or 5,
                    categories=user.categories or None,
                    hours=24,
                )
            logger.info(
                f"Digest for {user.email}: {len(articles)} articles "
                f"(min_score={user.min_relevance}, cats={user.categories or 'all'})"
            )
            success = await send_daily_digest(user, articles)
            if success:
                logger.info(f"Digest sent to {user.email}")
            else:
                logger.error(f"Digest FAILED for {user.email} — check RESEND_API_KEY and FROM_EMAIL")

        # Send sequentially with a 1s gap — Resend free tier allows 2 req/sec
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
            "arXiv", "NewsAPI", "Medium", "platformengineering.org",
            "Anthropic Blog", "OpenAI Blog", "Google DeepMind",
            "Google Research", "AWS AI Blog", "Google AI Blog", "MIT AI News",
        ],
    }



@app.post("/api/reprocess-rivals")
async def reprocess_rivals():
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
async def trigger_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh_news_job)
    return {"message": "News refresh triggered"}


@app.post("/api/trigger-digest")
async def trigger_digest(background_tasks: BackgroundTasks):
    background_tasks.add_task(send_digest_job)
    return {"message": "Digest triggered"}
