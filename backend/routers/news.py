from fastapi import APIRouter, Query
from database import get_db
from typing import Optional

router = APIRouter()

@router.get("")
async def get_news(
    limit: int = Query(20, le=100),
    offset: int = 0,
    category: Optional[str] = None,
    source: Optional[str] = None,
    min_relevance: int = Query(0, ge=0, le=10),
    search: Optional[str] = None,
):
    async with get_db() as db:
        articles = await db.get_articles(
            limit=limit, offset=offset, category=category,
            source=source, min_relevance=min_relevance, search=search
        )
    return {"articles": articles, "count": len(articles)}

@router.get("/stats")
async def get_stats():
    async with get_db() as db:
        return await db.get_stats()

@router.get("/categories")
async def get_categories():
    return {
        "categories": [
            "Product/Tool", "AI Model", "Research Paper",
            "Industry News", "Tutorial/Guide", "Platform/Infrastructure"
        ]
    }

@router.get("/sources")
async def get_sources():
    return {
        "sources": ["Hacker News", "arXiv", "Medium", "NewsAPI"]
    }
