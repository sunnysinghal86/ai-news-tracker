"""
Summarizer - Uses Claude API to:
1. Summarize articles (2-3 sentence digest)
2. Categorize: Product/Tool/Model/Research/News
3. Competitor analysis for products/tools/models
"""

import os
import asyncio
import aiohttp
import json
import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

CATEGORY_TYPES = ["Product/Tool", "AI Model", "Research Paper", "Industry News", "Tutorial/Guide", "Platform/Infrastructure"]

@dataclass
class ProcessedArticle:
    id: str
    title: str
    url: str
    source: str
    published_at: str
    author: str
    score: int
    # AI-generated fields
    summary: str = ""
    category: str = "Industry News"
    tags: List[str] = None
    # Competitor analysis (only for Product/Tool/Model)
    is_product_or_tool: bool = False
    product_name: str = ""
    competitors: List[dict] = None  # [{name, description, comparison}]
    competitive_advantage: str = ""
    relevance_score: int = 5  # 1-10 for software dev / platform eng


async def call_claude(prompt: str, system: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Call Claude API"""
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        return None
    
    try:
        payload = {
            "model": "claude-haiku-4-5-20251001",  # Cost-effective for batch processing
            "max_tokens": 600,
            "system": system,
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        async with session.post(ANTHROPIC_API_URL, json=payload, headers=headers) as resp:
            data = await resp.json()
            return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


SYSTEM_PROMPT = """You are an expert AI/ML analyst specializing in software development and platform engineering.
You analyze AI news articles and provide structured analysis. Always respond with valid JSON only, no markdown."""


async def analyze_article(article, session: aiohttp.ClientSession) -> ProcessedArticle:
    """Process a single article with Claude"""
    prompt = f"""Analyze this AI/tech article and return JSON:

Title: {article.title}
Source: {article.source}
Content: {article.content[:600]}

Return this exact JSON structure:
{{
  "summary": "2-3 sentence summary focused on what matters for software engineers and platform engineers",
  "category": "one of: Product/Tool | AI Model | Research Paper | Industry News | Tutorial/Guide | Platform/Infrastructure",
  "tags": ["tag1", "tag2", "tag3"],
  "relevance_score": <1-10 score for software dev / platform engineering relevance>,
  "is_product_or_tool": <true if this is about a product, tool, model, framework, or platform>,
  "product_name": "<name if is_product_or_tool, else empty string>",
  "competitors": [
    {{
      "name": "Competitor Name",
      "description": "brief description",
      "comparison": "how this new thing differs or improves on this competitor"
    }}
  ],
  "competitive_advantage": "<if is_product_or_tool: what makes it stand out vs competitors, else empty string>"
}}

For competitors: only include if is_product_or_tool is true. List 2-3 most relevant competitors max."""

    result = await call_claude(prompt, SYSTEM_PROMPT, session)
    
    processed = ProcessedArticle(
        id=article.id,
        title=article.title,
        url=article.url,
        source=article.source,
        published_at=article.published_at.isoformat() if hasattr(article.published_at, 'isoformat') else str(article.published_at),
        author=article.author,
        score=article.score,
        tags=article.tags or []
    )
    
    if result:
        try:
            # Strip any markdown code fences just in case
            clean = result.strip().strip("```json").strip("```").strip()
            data = json.loads(clean)
            processed.summary = data.get("summary", "")
            processed.category = data.get("category", "Industry News")
            processed.tags = data.get("tags", article.tags or [])
            processed.relevance_score = data.get("relevance_score", 5)
            processed.is_product_or_tool = data.get("is_product_or_tool", False)
            processed.product_name = data.get("product_name", "")
            processed.competitors = data.get("competitors", []) if processed.is_product_or_tool else []
            processed.competitive_advantage = data.get("competitive_advantage", "")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error for {article.title[:40]}: {e}")
            processed.summary = f"Article from {article.source}: {article.title}"
    
    return processed


async def summarize_articles(articles, max_concurrent: int = 5) -> List[ProcessedArticle]:
    """Process all articles with rate limiting"""
    if not ANTHROPIC_API_KEY:
        logger.warning("No API key - returning articles without AI analysis")
        return [ProcessedArticle(
            id=a.id, title=a.title, url=a.url, source=a.source,
            published_at=a.published_at.isoformat() if hasattr(a.published_at, 'isoformat') else str(a.published_at),
            author=a.author, score=a.score, tags=a.tags or [],
            summary=a.content[:200] if a.content else ""
        ) for a in articles]
    
    semaphore = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async def process_with_semaphore(article, session):
        async with semaphore:
            return await analyze_article(article, session)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [process_with_semaphore(a, session) for a in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Article processing failed: {r}")
        else:
            processed.append(r)
    
    return processed


def analyze_competitors(article_data: dict) -> dict:
    """Sync wrapper for on-demand competitor analysis (used by API)"""
    return article_data  # Already embedded in processed article
