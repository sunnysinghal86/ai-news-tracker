from fastapi import APIRouter
import os

router = APIRouter()

@router.get("")
async def get_config():
    return {
        "news_api_configured": bool(os.getenv("NEWS_API_KEY")),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "resend_configured": bool(os.getenv("RESEND_API_KEY")),
        "refresh_interval_hours": 1,
        "digest_time_utc": "08:00",
        "max_users": 20,
        "sources": ["Hacker News", "arXiv", "Medium", "NewsAPI"]
    }
