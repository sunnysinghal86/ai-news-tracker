import os
import aiohttp
import logging
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_config():
    return {
        "news_api_configured":    bool(os.getenv("NEWS_API_KEY")),
        "anthropic_configured":   bool(os.getenv("ANTHROPIC_API_KEY")),
        "resend_configured":      bool(os.getenv("RESEND_API_KEY")),
        "refresh_interval_hours": 1,
        "digest_time_utc":        "08:00",
        "max_users":              20,
        "sources": [
            "Hacker News", "arXiv", "Medium", "NewsAPI",
            "platformengineering.org", "Platform Weekly"
        ],
    }


@router.get("/debug-claude")
async def debug_claude():
    """Test Claude API connection live."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "status": "error",
            "reason": "ANTHROPIC_API_KEY not set",
            "fix": "Render dashboard → Environment → add ANTHROPIC_API_KEY"
        }
    try:
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": 'Reply with exactly: {"ok": true}'}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
        if resp.status == 200:
            return {
                "status": "ok",
                "response": data.get("content", [{}])[0].get("text", ""),
                "key_prefix": api_key[:12] + "...",
            }
        return {
            "status": "error",
            "http_status": resp.status,
            "error": data.get("error", data),
        }
    except Exception as e:
        return {"status": "error", "exception": str(e)}
