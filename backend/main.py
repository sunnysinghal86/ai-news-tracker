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
from emailer import send_daily_digest
from routers import news, users, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler.add_job(refresh_news_job, "interval", hours=1,
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
                    name, email = entry.split(":", 1)
                    await db.create_user(email=email.strip(), name=name.strip())
                    logger.info(f"Seeded subscriber: {email.strip()}")

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
        articles = await fetch_all_news()
        logger.info(f"Fetched {len(articles)} articles")
        articles = await enrich_all(articles)
        logger.info("Enrichment done")
        processed = await summarize_articles(articles)
        logger.info(f"Summarised {len(processed)} articles")
        async with get_db() as db:
            await db.upsert_articles(processed)
        logger.info("News refresh complete")
    except Exception as e:
        logger.error(f"News refresh failed: {e}", exc_info=True)


async def send_digest_job():
    logger.info("Sending daily digest...")
    try:
        async with get_db() as db:
            active_users = await db.get_active_users()
            top_articles = await db.get_top_articles(limit=10)
        for user in active_users:
            await send_daily_digest(user, top_articles)
            logger.info(f"Digest sent to {user.email}")
    except Exception as e:
        logger.error(f"Digest failed: {e}", exc_info=True)


@app.get("/")
async def root():
    return {"status": "online", "service": "AI News Tracker"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/trigger-refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh_news_job)
    return {"message": "News refresh triggered"}


@app.post("/api/trigger-digest")
async def trigger_digest(background_tasks: BackgroundTasks):
    background_tasks.add_task(send_digest_job)
    return {"message": "Digest triggered"}
