"""
AI News Tracker - FastAPI Backend
Tracks AI/ML news from HN, arXiv, NewsAPI, Medium RSS
Summarizes with Claude, sends daily email digests
"""

import os
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, get_db
from news_fetcher import fetch_all_news
from summarizer import summarize_articles, analyze_competitors
from emailer import send_daily_digest
from models import User, EmailConfig, NewsItem
from routers import news, users, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    
    # Schedule news refresh every 1 hour
    scheduler.add_job(
        refresh_news_job,
        "interval",
        hours=1,
        id="refresh_news",
        replace_existing=True
    )
    
    # Schedule daily digest at 8am UTC
    scheduler.add_job(
        send_digest_job,
        "cron",
        hour=8,
        minute=0,
        id="daily_digest",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Scheduler started. News refresh: every 1hr | Digest: daily 8am UTC")

    # Seed subscribers from SEED_SUBSCRIBERS env var (survives ephemeral filesystem)
    # Format: "Alice:alice@example.com,Bob:bob@example.com"
    seed = os.getenv("SEED_SUBSCRIBERS", "")
    if seed:
        async with get_db() as db:
            for entry in seed.split(","):
                entry = entry.strip()
                if ":" in entry:
                    name, email = entry.split(":", 1)
                    await db.create_user(email=email.strip(), name=name.strip())
                    logger.info(f"✅ Seeded subscriber: {email.strip()}")

    # Initial fetch on startup
    asyncio.create_task(refresh_news_job())
    
    yield
    
    # Shutdown
    scheduler.shutdown()

app = FastAPI(
    title="AI News Tracker",
    description="Track AI/ML news with summaries, competitor analysis, and email digests",
    version="1.0.0",
    lifespan=lifespan
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Set ALLOWED_ORIGINS=https://yourapp.onrender.com in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Include routers
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(config.router, prefix="/api/config", tags=["config"])


async def refresh_news_job():
    """Fetch latest news from all sources and process with AI"""
    logger.info("🔄 Starting news refresh...")
    try:
        articles = await fetch_all_news()
        logger.info(f"📰 Fetched {len(articles)} articles")
        
        # Summarize and analyze in batches
        processed = await summarize_articles(articles)
        logger.info(f"🤖 Processed {len(processed)} articles with AI")
        
        # Store to DB
        async with get_db() as db:
            await db.upsert_articles(processed)
        
        logger.info("✅ News refresh complete")
    except Exception as e:
        logger.error(f"❌ News refresh failed: {e}")


async def send_digest_job():
    """Send daily email digest to all subscribed users"""
    logger.info("📧 Sending daily digest...")
    try:
        async with get_db() as db:
            users = await db.get_active_users()
            top_articles = await db.get_top_articles(limit=10)
        
        for user in users:
            await send_daily_digest(user, top_articles)
            logger.info(f"✅ Digest sent to {user.email}")
    except Exception as e:
        logger.error(f"❌ Daily digest failed: {e}")


@app.get("/")
async def root():
    return {"status": "online", "service": "AI News Tracker"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/trigger-refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Manually trigger a news refresh"""
    background_tasks.add_task(refresh_news_job)
    return {"message": "News refresh triggered"}

@app.post("/api/trigger-digest")
async def trigger_digest(background_tasks: BackgroundTasks):
    """Manually trigger the daily digest"""
    background_tasks.add_task(send_digest_job)
    return {"message": "Digest send triggered"}
