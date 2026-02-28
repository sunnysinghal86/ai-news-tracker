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
        logger.warning("No ANTHROPIC_API_KEY - summaries unavailable. Set the key to enable AI summaries.")
        return [ProcessedArticle(
            id=a.id, title=a.title, url=a.url, source=a.source,
            published_at=a.published_at.isoformat() if hasattr(a.published_at, 'isoformat') else str(a.published_at),
            author=a.author, score=a.score, tags=a.tags or [],
            summary=a.content[:300].strip() if a.content and len(a.content) > 30
                    else f"From {a.source}. Click the headline to read the full article.",
            relevance_score=5,
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


async def enrich_article_content(article: RawArticle, session: aiohttp.ClientSession) -> RawArticle:
    """
    For articles with no body text (most HN/NewsAPI items are title+URL only),
    fetch the page and extract og:description / meta description as a content stub.
    This gives Claude enough context to write a meaningful summary.
    """
    if article.content and len(article.content) > 80:
        return article  # Already has content
    if not article.url or article.url.startswith("https://news.ycombinator.com"):
        return article  # Skip HN comment pages

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AISignalBot/1.0)"}
        async with session.get(article.url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=8),
                               allow_redirects=True) as resp:
            if resp.status != 200:
                return article
            ct = resp.headers.get("content-type", "")
            if "html" not in ct:
                return article
            html = await resp.text(errors="ignore")

        # Extract og:description or meta description (no heavy parser needed)
        import re
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
        pass  # Silently skip — enrichment is best-effort

    return article


async def enrich_all(articles: List[RawArticle]) -> List[RawArticle]:
    """Enrich up to 40 articles concurrently (best-effort meta description fetch)"""
    sem = asyncio.Semaphore(10)
    timeout = aiohttp.ClientTimeout(total=10)
    connector = aiohttp.TCPConnector(limit=20)

    async def bounded(article, session):
        async with sem:
            return await enrich_article_content(article, session)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        results = await asyncio.gather(
            *[bounded(a, session) for a in articles],
            return_exceptions=True
        )

    enriched = []
    for r in results:
        if isinstance(r, Exception):
            enriched.append(articles[len(enriched)])  # fallback to original
        else:
            enriched.append(r)
    return enriched
