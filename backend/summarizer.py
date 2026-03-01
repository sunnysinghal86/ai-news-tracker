"""
Summarizer - Uses Claude Haiku to summarize articles and run competitor analysis.
"""

import os
import re
import asyncio
import aiohttp
import json
import logging
from typing import List, Optional
from dataclasses import dataclass

# RawArticle is defined in news_fetcher — import it to fix the NameError crash
from news_fetcher import RawArticle

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You are an expert AI/ML analyst specialising in software development and platform engineering. "
    "Analyse AI/tech news articles and return structured JSON only — no markdown, no preamble."
)


@dataclass
class ProcessedArticle:
    id: str
    title: str
    url: str
    source: str
    published_at: str
    author: str
    score: int
    summary: str = ""
    category: str = "Industry News"
    tags: Optional[List[str]] = None
    is_product_or_tool: bool = False
    product_name: str = ""
    competitors: Optional[List[dict]] = None
    competitive_advantage: str = ""
    relevance_score: int = 5


# ── Content enrichment ────────────────────────────────────────────────────────

async def _enrich_one(article: RawArticle, session: aiohttp.ClientSession) -> RawArticle:
    """Fetch og:description from the article URL when we have no body text."""
    if article.content and len(article.content) > 80:
        return article
    if not article.url or "news.ycombinator.com" in article.url:
        return article

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AISignalBot/1.0)"}
        async with session.get(
            article.url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return article
            if "html" not in resp.headers.get("content-type", ""):
                return article
            html = await resp.text(errors="ignore")

        patterns = [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                desc = m.group(1).strip()[:500]
                if len(desc) > 40:
                    article.content = desc
                    return article
    except Exception:
        pass  # best-effort — silently skip

    return article


async def enrich_all(articles: List[RawArticle]) -> List[RawArticle]:
    """Concurrently enrich articles that have no body text."""
    sem = asyncio.Semaphore(10)
    connector = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=10)

    async def bounded(art: RawArticle, session: aiohttp.ClientSession) -> RawArticle:
        async with sem:
            return await _enrich_one(art, session)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        results = await asyncio.gather(
            *[bounded(a, session) for a in articles],
            return_exceptions=True,
        )

    enriched = []
    for i, r in enumerate(results):
        enriched.append(articles[i] if isinstance(r, Exception) else r)
    return enriched


# ── Claude API ────────────────────────────────────────────────────────────────

async def _call_claude(prompt: str, session: aiohttp.ClientSession) -> Optional[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")  # read fresh — not cached at import
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude call")
        return None
    try:
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with session.post(ANTHROPIC_API_URL, json=payload, headers=headers) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"Claude API HTTP {resp.status}: {data.get('error', data)}")
                return None
            return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


async def _analyse_article(article: RawArticle, session: aiohttp.ClientSession) -> ProcessedArticle:
    prompt = (
        "Analyse this AI/tech article and return ONLY valid JSON. No markdown, no explanation.\n\n"
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"Content: {(article.content or '')[:600]}\n\n"
        "Rules:\n"
        "- is_product_or_tool = true for ANY tool, library, framework, platform, model, API, or service\n"
        "- If is_product_or_tool is true, include 2-3 REAL named competitors with specific comparisons\n"
        "- relevance_score: 8-10 for platform eng/MLOps/AI infra, 5-7 general AI news, 1-4 unrelated\n\n"
        "Return exactly this JSON:\n"
        "{\n"
        '"  \"summary\": \"2-3 sentences for software/platform engineers, be specific\",\n"' 
        '"  \"category\": \"Product/Tool | AI Model | Research Paper | Industry News | Tutorial/Guide | Platform/Infrastructure\",\n"'
        '"  \"tags\": [\"tag1\", \"tag2\", \"tag3\"],\n"'
        '"  \"relevance_score\": <integer 1-10>,\n"'
        '"  \"is_product_or_tool\": <true or false>,\n"'
        '"  \"product_name\": \"<product name or empty string>\",\n"'
        '"  \"competitors\": [{{\"name\": \"Real Name\", \"description\": \"what they do\", \"comparison\": \"how this differs\"}}],\n"'
        '"  \"competitive_advantage\": \"<key differentiator or empty string>\"\n"'
        "}"
    )

    base = ProcessedArticle(
        id=article.id,
        title=article.title,
        url=article.url,
        source=article.source,
        published_at=(
            article.published_at.isoformat()
            if hasattr(article.published_at, "isoformat")
            else str(article.published_at)
        ),
        author=article.author,
        score=article.score,
        tags=list(article.tags or []),
    )

    raw = await _call_claude(prompt, session)
    if not raw:
        base.summary = article.content[:300].strip() if article.content else ""
        return base

    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)
        base.summary = data.get("summary", "")
        base.category = data.get("category", "Industry News")
        base.tags = data.get("tags", list(article.tags or []))
        base.relevance_score = int(data.get("relevance_score", 5))
        base.is_product_or_tool = bool(data.get("is_product_or_tool", False))
        base.product_name = data.get("product_name", "")
        base.competitors = data.get("competitors", []) if base.is_product_or_tool else []
        base.competitive_advantage = data.get("competitive_advantage", "")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON parse error for '{article.title[:40]}': {e}")
        base.summary = article.content[:300].strip() if article.content else ""

    return base


# ── Public entry point ────────────────────────────────────────────────────────

async def summarize_articles(articles: List[RawArticle], max_concurrent: int = 5) -> List[ProcessedArticle]:
    if not os.getenv("ANTHROPIC_API_KEY", ""):
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI summaries")
        return [
            ProcessedArticle(
                id=a.id, title=a.title, url=a.url, source=a.source,
                published_at=(
                    a.published_at.isoformat()
                    if hasattr(a.published_at, "isoformat")
                    else str(a.published_at)
                ),
                author=a.author, score=a.score,
                tags=list(a.tags or []),
                summary=(
                    a.content[:300].strip()
                    if a.content and len(a.content) > 30
                    else f"From {a.source} — click the headline to read."
                ),
            )
            for a in articles
        ]

    sem = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=30)

    async def bounded(art: RawArticle, session: aiohttp.ClientSession) -> ProcessedArticle:
        async with sem:
            return await _analyse_article(art, session)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            *[bounded(a, session) for a in articles],
            return_exceptions=True,
        )

    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Article processing failed: {r}")
            a = articles[i]
            out.append(ProcessedArticle(
                id=a.id, title=a.title, url=a.url, source=a.source,
                published_at=str(a.published_at), author=a.author, score=a.score,
                tags=list(a.tags or []),
                summary=a.content[:300] if a.content else "",
            ))
        else:
            out.append(r)
    return out
