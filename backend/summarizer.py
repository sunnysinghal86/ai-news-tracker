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
import trafilatura

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
    """
    Extract full article body using trafilatura.
    Falls back to og:description if trafilatura gets nothing.
    """
    if article.content and len(article.content) > 200:
        return article  # already has good content

    if not article.url or "news.ycombinator.com" in article.url:
        return article

    # Skip known paywalled domains
    paywalled = ["wsj.com", "ft.com", "bloomberg.com", "nytimes.com", "economist.com"]
    if any(d in article.url for d in paywalled):
        return article

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        }
        async with session.get(
            article.url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return article
            if "html" not in resp.headers.get("content-type", ""):
                return article
            html = await resp.text(errors="ignore")

        # Attempt 1: trafilatura full body extraction
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )
        if extracted and len(extracted.strip()) > 150:
            article.content = extracted.strip()[:1500]
            logger.debug(f"trafilatura: {len(article.content)} chars for {article.title[:50]}")
            return article

        # Attempt 2: og:description / meta description fallback
        import re as _re
        patterns = [
            r'<meta[^>]+property=[\x27"]{1,2}og:description[\x27"]{1,2}[^>]+content=[\x27"]{1,2}(.*?)[\x27"]{1,2}',
            r'<meta[^>]+name=[\x27"]{1,2}description[\x27"]{1,2}[^>]+content=[\x27"]{1,2}(.*?)[\x27"]{1,2}',
        ]
        for pat in patterns:
            m = _re.search(pat, html, _re.IGNORECASE | _re.DOTALL)
            if m:
                desc = m.group(1).strip()[:600]
                if len(desc) > 40:
                    article.content = desc
                    return article

    except Exception as e:
        logger.debug(f"Enrichment failed for {article.url[:60]}: {e}")

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

async def _call_claude(prompt: str, session: aiohttp.ClientSession, retries: int = 4) -> Optional[str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude call")
        return None

    payload = {
        "model": os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        "max_tokens": 550,  # 550 — cutoff was at ~425, need headroom for longer articles
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    for attempt in range(retries):
        try:
            async with session.post(ANTHROPIC_API_URL, json=payload, headers=headers) as resp:
                data = await resp.json()

                if resp.status == 200:
                    return data.get("content", [{}])[0].get("text", "")

                if resp.status == 429:
                    # Rate limited — exponential backoff: 15s, 30s, 60s, 120s
                    wait = 15 * (2 ** attempt)
                    logger.warning(f"Rate limited (429) — waiting {wait}s before retry {attempt+1}/{retries}")
                    await asyncio.sleep(wait)
                    continue

                logger.error(f"Claude API HTTP {resp.status}: {data.get('error', data)}")
                return None

        except Exception as e:
            logger.error(f"Claude API error (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)

    logger.error("Claude API failed after all retries")
    return None


async def _analyse_article(article: RawArticle, session: aiohttp.ClientSession) -> ProcessedArticle:
    content_text = (article.content or "")[:1200]
    prompt = (
        "Analyse this AI/tech article. Return ONLY valid JSON, no markdown.\n"
        f"Title: {article.title}\nSource: {article.source}\nContent: {content_text}\n\n"
        f"{'IMPORTANT: This is from MIT AI News — category MUST be Research Paper.\n' if article.source == 'MIT AI News' else ''}"
        "Pick category (use EXACT name only):\n"
        "  Product/Tool — SDK, library, framework, CLI, SaaS, developer tool\n"
        "  AI Model — LLM, image model, embedding model, AI system\n"
        "  Research Paper — academic paper, preprint, study\n"
        "  Tutorial/Guide — how-to, guide, best practices\n"
        "  Platform/Infrastructure — MLOps, deployment, cloud AI, DevOps\n"
        "  Industry News — funding, acquisition, company news, opinion\n"
        "is_product_or_tool: set true if article is about a specific named product, tool, model, "
        "framework, SDK, platform, or service — NOT for general news or opinion.\n"
        "If is_product_or_tool=true, you MUST include 2-3 real named competitors with "
        "specific comparisons. Do not leave competitors empty.\n"
        "relevance: 9-10=AI infra/MLOps, 7-8=major model/framework, 5-6=AI news, 1-4=weak\n\n"
        '{"summary":"2-3 sentences focused on what changed and why it matters for engineers",'
        '"category":"<EXACT name from list above, no extra text>",'
        '"tags":["t1","t2","t3"],'
        '"relevance_score":<1-10>,'
        '"is_product_or_tool":<bool>,'
        '"product_name":"<name or empty>",'
        '"competitors":[{"name":"Competitor Name","description":"what they do","comparison":"how this differs"}],'
        '"competitive_advantage":"one specific differentiator"}'
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

async def summarize_articles(articles: List[RawArticle], max_concurrent: int = 1) -> List[ProcessedArticle]:
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

    # Cap is now applied in main.py before enrichment — articles arriving here
    # are already the top 30 by score. Log a warning if somehow more arrive.
    if len(articles) > 30:
        logger.warning(f"Received {len(articles)} articles — expected max 30. Capping.")
        articles = articles[:30]

    sem = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=400)  # ~6.5 min — 30 articles × 4s + Claude latency buffer

    async def bounded(art: RawArticle, session: aiohttp.ClientSession, idx: int = 0) -> ProcessedArticle:
        async with sem:
            # Fixed 4s gap between calls: 600 tokens × 15/min = 9,000 tokens/min (under 10k limit)
            if idx > 0:
                await asyncio.sleep(4)
            return await _analyse_article(art, session)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            *[bounded(a, session, idx=i) for i, a in enumerate(articles)],
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
