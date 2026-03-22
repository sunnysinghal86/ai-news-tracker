"""
News Fetcher - Pulls from Hacker News, arXiv, NewsAPI, Medium RSS
Focus: AI/ML, Software Development, Platform Engineering
"""

import aiohttp
import asyncio
import feedparser
import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Keywords for filtering relevant articles
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "LLM", "large language model",
    "GPT", "Claude", "Gemini", "Llama", "transformer", "neural network",
    "generative AI", "foundation model", "RAG", "vector database",
    # Software Dev / Platform Eng focus
    "MLOps", "LLMOps", "AI platform", "AI infrastructure", "model deployment",
    "inference", "fine-tuning", "embeddings", "AI agent", "agentic",
    "kubernetes AI", "cloud AI", "AI observability", "AI gateway",
    "openai", "anthropic", "mistral", "cohere", "hugging face",
    "langchain", "llamaindex", "dspy", "crewai", "autogen",
    "platform engineering", "developer platform", "AI tooling", "AI SDK",
    # New model/product launch terms (important for new sources)
    "model release", "benchmark", "multimodal", "reasoning model",
    "o1", "o3", "claude 3", "claude 4", "gpt-4", "gpt-5", "gemini 2",
    "diffusion model", "text-to-image", "text-to-video", "AI startup",
    "series a", "series b", "raises", "launches", "announces", "unveils",
    "bedrock", "sagemaker", "vertex ai", "azure ai", "AI safety",
    "context window", "tokens", "open source model", "weights"
]

# ── High-value keywords that signal important AI/platform engineering content ──
# Used for pre-Claude scoring only — weights title relevance before Claude sees it
HIGH_SIGNAL_KEYWORDS = [
    # Model/product launches
    "launches", "releases", "announces", "unveils", "introduces",
    "new model", "new version", "open source", "open-source",
    # Performance signals
    "beats", "outperforms", "state of the art", "sota", "benchmark",
    # Specific technologies relevant to our audience
    "claude", "gemini", "llama", "mistral", "gpt",
    "agent", "multimodal", "reasoning", "rag", "fine-tuning",
    "kubernetes", "platform engineering", "mlops", "inference",
    "langchain", "llamaindex", "bedrock", "sagemaker",
    # Business signals
    "raises", "funding", "acquired", "open source",
]

# Modest source bonus — not to favour sources but to counteract
# keyword-stuffed titles from community/tutorial sources like Medium.
# Research sources get a small boost because their titles are academic
# (no marketing keywords) but content is high quality.
SOURCE_BONUS = {
    "arXiv":                    3,   # academic titles lack keywords — needs a nudge
    "MIT AI News":              2,
    "Anthropic Blog":           2,   # official announcements, factual titles
    "OpenAI Blog":              2,
    "Google DeepMind":          2,
    "Google AI Blog":           2,
    "Google Research":          2,
    "AWS AI Blog":              1,
    "platformengineering.org":  1,
    "NewsAPI":                  0,
    "Medium":                   0,   # already benefits from keyword-rich titles
}

def quality_score(article: "RawArticle") -> float:
    """
    Pre-Claude quality score — decides which 20 articles get sent to Claude.

    Problem: without source weighting, keyword-stuffed Medium titles dominate
    because Medium writers optimise for buzzwords ("AI agent", "LLM reasoning").
    Academic/official sources have plain descriptive titles and score poorly.

    Solution: small source bonus to counteract title-keyword bias, NOT to
    prefer sources by brand. arXiv gets +3 because its titles are academic,
    not because arXiv is "better" than Medium per se.

    Factors:
    1. HN upvotes — strongest objective quality signal (community-validated)
    2. Title keywords — topic relevance to platform/AI engineers
    3. Small source bonus — counteracts title-keyword gaming
    4. Recency — newer is more useful
    """
    score = 0.0

    # 1. HN upvote score (0–10)
    if article.score > 0:
        score += min(10.0, article.score / 50)

    # 2. Title keywords (0–6)
    title_lower = article.title.lower()
    kw_hits = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw in title_lower)
    score += min(3.0, kw_hits * 1.0)  # capped at 3 — prevents keyword stuffing dominance

    # 3. Small source bonus to counteract keyword-stuffed titles (0–3)
    score += SOURCE_BONUS.get(article.source, 0)

    # 4. Recency (0–3)
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    age = now - article.published_at if article.published_at.tzinfo else timedelta(days=7)
    if age < timedelta(hours=12):
        score += 3.0
    elif age < timedelta(hours=24):
        score += 2.0
    elif age < timedelta(days=3):
        score += 1.0

    return score

    return score


@dataclass
class RawArticle:
    id: str
    title: str
    url: str
    source: str
    published_at: datetime
    content: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    score: int = 0  # HN score or relevance


def gen_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def strip_html(text: str) -> str:
    """Strip HTML tags and decode entities to plain text."""
    import re as _re
    text = _re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    text = _re.sub(r'&#\d+;', '', text)
    text = _re.sub(r'\s+', ' ', text).strip()
    return text[:500]  # cap at 500 chars for storage


def fix_encoding(text: str) -> str:
    """Fix mojibake — UTF-8 bytes misread as latin-1 (common in RSS feeds)."""
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def is_relevant(title: str, content: str = "") -> bool:
    text = (title + " " + content).lower()
    return any(kw.lower() in text for kw in AI_KEYWORDS)


# ─────────────────────────────────────────────
# HACKER NEWS
# ─────────────────────────────────────────────
async def fetch_hackernews(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch top AI/ML stories from HN Algolia search API"""
    articles = []
    try:
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": "AI machine learning LLM platform engineering",
            "tags": "story",
            "numericFilters": "points>10",
            "hitsPerPage": 30,
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            for hit in data.get("hits", []):
                if not is_relevant(hit.get("title", ""), hit.get("story_text", "") or ""):
                    continue
                created = hit.get("created_at", "")
                try:
                    published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except:
                    published = datetime.now(timezone.utc)
                
                articles.append(RawArticle(
                    id=gen_id(hit.get("url", hit.get("objectID", ""))),
                    title=hit.get("title", ""),
                    url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    source="Hacker News",
                    published_at=published,
                    content=fix_encoding(strip_html(hit.get("story_text", "") or "")),
                    author=hit.get("author", ""),
                    tags=["hacker-news"],
                    score=hit.get("points", 0)
                ))
        logger.info(f"HN: {len(articles)} articles")
    except Exception as e:
        logger.error(f"HN fetch error: {e}")
    return articles


# ─────────────────────────────────────────────
# arXiv
# ─────────────────────────────────────────────
async def fetch_arxiv(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch latest AI papers from arXiv — uses its own session to avoid shared timeout."""
    articles = []
    try:
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 15,
            "start": 0,
        }
        # arXiv gets its own session — avoids shared 30s timeout being consumed
        # by concurrent requests to other sources
        arxiv_timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=arxiv_timeout) as arxiv_session:
            async with arxiv_session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"arXiv returned HTTP {resp.status}")
                    return []
                text = await resp.text()
        
        feed = feedparser.parse(text)
        for entry in feed.entries:
            title = entry.get("title", "").replace("\n", " ")
            abstract = entry.get("summary", "").replace("\n", " ")
            
            published_str = entry.get("published", "")
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except:
                published = datetime.now(timezone.utc)
            
            articles.append(RawArticle(
                id=gen_id(entry.get("id", "")),
                title=title,
                url=entry.get("id", ""),
                source="arXiv",
                published_at=published,
                content=abstract,
                author=", ".join([a.get("name", "") for a in entry.get("authors", [])[:3]]),
                tags=["research", "arxiv"],
                score=0
            ))
        logger.info(f"arXiv: {len(articles)} papers")
    except Exception as e:
        logger.error(f"arXiv fetch error: {e}")
    return articles


# ─────────────────────────────────────────────
# NewsAPI
# ─────────────────────────────────────────────
async def fetch_newsapi(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch from NewsAPI (requires free API key)"""
    if not NEWS_API_KEY:
        logger.warning("NewsAPI key not set, skipping")
        return []
    
    articles = []
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "AI OR LLM OR \"machine learning\" OR \"platform engineering\" OR MLOps",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": NEWS_API_KEY,
        }
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        
        for item in data.get("articles", []):
            title = fix_encoding(item.get("title", "") or "") or ""
            desc = item.get("description", "") or ""
            if not is_relevant(title, desc):
                continue
            
            pub = item.get("publishedAt", "")
            try:
                published = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except:
                published = datetime.now(timezone.utc)
            
            source_name = item.get("source", {}).get("name", "NewsAPI")
            articles.append(RawArticle(
                id=gen_id(item.get("url", "")),
                title=title,
                url=item.get("url", ""),
                source=f"NewsAPI / {source_name}",
                published_at=published,
                content=strip_html(desc),
                author=item.get("author", ""),
                tags=["news"],
                score=0
            ))
        logger.info(f"NewsAPI: {len(articles)} articles")
    except Exception as e:
        logger.error(f"NewsAPI fetch error: {e}")
    return articles


# ─────────────────────────────────────────────
# Medium RSS (via RSS2JSON or direct)
# ─────────────────────────────────────────────
MEDIUM_FEEDS = [
    "https://medium.com/feed/tag/artificial-intelligence",
    "https://medium.com/feed/tag/mlops",
]

async def fetch_medium(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch AI articles from Medium RSS feeds"""
    articles = []
    for feed_url in MEDIUM_FEEDS:
        try:
            # Use rss2json proxy (free, no auth needed)
            proxy = f"https://api.rss2json.com/v1/api.json?rss_url={feed_url}&count=5"
            async with session.get(proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
            
            for item in data.get("items", []):
                title = fix_encoding(item.get("title", "") or "")
                if not is_relevant(title, item.get("description", "")):
                    continue
                
                pub = item.get("pubDate", "")
                try:
                    published = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except:
                    published = datetime.now(timezone.utc)
                
                articles.append(RawArticle(
                    id=gen_id(item.get("link", "")),
                    title=title,
                    url=item.get("link", ""),
                    source="Medium",
                    published_at=published,
                    content=fix_encoding(strip_html(item.get("description", "") or "")),
                    author=item.get("author", ""),
                    tags=["medium"],
                    score=0
                ))
        except Exception as e:
            logger.warning(f"Medium feed {feed_url} error: {e}")
    
    logger.info(f"Medium: {len(articles)} articles")
    return articles




# ─────────────────────────────────────────────
# PLATFORM ENGINEERING SOURCES
# ─────────────────────────────────────────────
PLATFORM_RSS_FEEDS = [
    # platformengineering.org - official community RSS
    ("https://platformengineering.org/blog/rss.xml", "platformengineering.org"),
]

# ── New AI news RSS sources ───────────────────────────────────────────────────
AI_NEWS_RSS_FEEDS = [
    # Company blogs — catch every model/product release on day one
    ("https://www.anthropic.com/rss.xml", "Anthropic Blog"),
    ("https://openai.com/news/rss.xml",                     "OpenAI Blog"),
    ("https://deepmind.google/blog/rss.xml",                "Google DeepMind"),
    ("https://research.google/blog/rss",                    "Google Research"),
    ("https://aws.amazon.com/blogs/machine-learning/feed/", "AWS AI Blog"),
    ("https://blog.google/technology/ai/rss/",              "Google AI Blog"),
    ("https://news.mit.edu/rss/topic/artificial-intelligence2", "MIT AI News"),
    # Industry coverage — product launches, funding, analysis
    # Research explainers for engineers
]


async def fetch_platform_sources(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch from platformengineering.org and Platform Weekly RSS"""
    articles = []
    for feed_url, source_name in PLATFORM_RSS_FEEDS:
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 (compatible; AISignalBot/1.0)"}
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"{source_name} returned HTTP {resp.status}")
                    continue
                text = await resp.text()

            feed = feedparser.parse(text)
            if not feed.entries:
                logger.warning(f"{source_name}: no entries in feed")
                continue

            for entry in feed.entries:
                title = fix_encoding(entry.get("title", "").replace("\n", " "))
                summary = fix_encoding(strip_html(
                    entry.get("summary", "") or entry.get("description", "")
                ))

                # Platform engineering sources are always relevant — no keyword filter
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    published = datetime.now(timezone.utc)

                url = entry.get("link", "")
                articles.append(RawArticle(
                    id=gen_id(url),
                    title=title,
                    url=url,
                    source=source_name,
                    published_at=published,
                    content=summary[:500],
                    author=entry.get("author", ""),
                    tags=["platform-engineering"],
                    score=0
                ))
            logger.info(f"{source_name}: {len(feed.entries)} articles")
        except Exception as e:
            logger.warning(f"{source_name} fetch error: {e}")

    return articles


async def fetch_anthropic(session: aiohttp.ClientSession) -> List[RawArticle]:
    """
    Fetch Anthropic blog posts via their sitemap.
    Anthropic has no official RSS feed — sitemap is the most reliable alternative.
    Filters to /news/ URLs only to avoid product pages, docs etc.
    """
    articles = []
    try:
        sitemap_url = "https://www.anthropic.com/sitemap.xml"
        async with session.get(
            sitemap_url,
            timeout=aiohttp.ClientTimeout(total=12),
            headers={"User-Agent": "Mozilla/5.0 (compatible; AISignalBot/1.0)"},
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Anthropic sitemap returned HTTP {resp.status}")
                return []
            text = await resp.text()

        # Parse sitemap XML — extract /news/ URLs with lastmod dates
        import re as _re
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        urls = _re.findall(r'<loc>(https://www\.anthropic\.com/news/[^<]+)</loc>', text)
        dates = _re.findall(r'<lastmod>([^<]+)</lastmod>', text)

        # Zip URLs with dates (sitemap entries are in order)
        for i, url in enumerate(urls[:20]):  # max 20 from sitemap
            try:
                # Parse date if available
                if i < len(dates):
                    from datetime import datetime as _dt
                    pub = _dt.fromisoformat(dates[i].replace("Z", "+00:00"))
                else:
                    pub = datetime.now(timezone.utc)

                if pub < cutoff:
                    continue

                # Extract slug as title placeholder — will be enriched by trafilatura
                slug = url.rstrip("/").split("/")[-1].replace("-", " ").title()

                articles.append(RawArticle(
                    id=gen_id(url),
                    title=slug,
                    url=url,
                    source="Anthropic Blog",
                    published_at=pub,
                    content="",   # trafilatura will enrich this
                    author="Anthropic",
                    tags=["anthropic", "ai"],
                    score=0,
                ))
            except Exception as e:
                logger.debug(f"Anthropic sitemap entry error: {e}")
                continue

        logger.info(f"Anthropic Blog: {len(articles)} articles (via sitemap)")
    except Exception as e:
        logger.warning(f"Anthropic sitemap fetch error: {e}")
    return articles

async def fetch_ai_news_rss(session: aiohttp.ClientSession) -> List[RawArticle]:
    """
    Fetch from company blogs and AI industry news RSS feeds.
    Covers: Anthropic, OpenAI, Google DeepMind, Google Research,
            AWS AI Blog, VentureBeat AI, TechCrunch AI, The Gradient.

    Uses is_relevant() keyword filter on all sources except company blogs
    (Anthropic/OpenAI/DeepMind/Google Research are always AI-relevant).
    """
    ALWAYS_RELEVANT = {"Anthropic Blog", "OpenAI Blog", "Google DeepMind", "Google Research", "Google AI Blog"}
    articles = []

    for feed_url, source_name in AI_NEWS_RSS_FEEDS:
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=12),
                headers={"User-Agent": "Mozilla/5.0 (compatible; AISignalBot/1.0)"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"{source_name} returned HTTP {resp.status}")
                    continue
                text = await resp.text()

            feed = feedparser.parse(text)
            if not feed.entries:
                logger.warning(f"{source_name}: no entries in feed")
                continue

            count = 0
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            for entry in feed.entries:
                title   = fix_encoding(entry.get("title", "").replace("\n", " ")).strip()
                summary = fix_encoding(strip_html(
                    entry.get("summary", "") or entry.get("description", "") or ""
                ))
                url = entry.get("link", "")

                if not title or not url:
                    continue

                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    published = datetime.now(timezone.utc)

                # Skip articles older than 30 days — prevents archive dumps (e.g. OpenAI 886 articles)
                if published < cutoff:
                    continue

                # Company blogs are always relevant — skip keyword filter
                # Industry sources (VentureBeat, TechCrunch etc) must pass keyword check
                if source_name not in ALWAYS_RELEVANT:
                    if not is_relevant(title, summary):
                        continue

                articles.append(RawArticle(
                    id=gen_id(url),
                    title=title,
                    url=url,
                    source=source_name,
                    published_at=published,
                    content=summary[:600],
                    author=fix_encoding(entry.get("author", "")),
                    tags=["ai-news"],
                    score=0,
                ))
                count += 1

            logger.info(f"{source_name}: {count} articles")

        except Exception as e:
            logger.warning(f"{source_name} fetch error: {e}")

    return articles


# ─────────────────────────────────────────────
# MAIN AGGREGATOR
# ─────────────────────────────────────────────
async def fetch_all_news() -> List[RawArticle]:
    """Fetch from all active sources concurrently.
    Active: arXiv, NewsAPI, PE.org, company blogs (OpenAI/DeepMind/Google/AWS/Anthropic), MIT AI News
    Removed: HN (rate limited), Medium (low quality), TechCrunch/Ars/Wired/Verge (removed by user)
    """
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=20)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        results = await asyncio.gather(
            fetch_arxiv(session),
            fetch_newsapi(session),
            fetch_medium(session),
            fetch_platform_sources(session),
            fetch_anthropic(session),
            fetch_ai_news_rss(session),
            return_exceptions=True
        )
    
    all_articles = []
    seen_ids = set()

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Source error: {result}")
            continue
        for article in result:
            if article.id not in seen_ids:
                seen_ids.add(article.id)
                all_articles.append(article)

    # Sort by quality score — source authority + title keywords + recency
    all_articles.sort(key=quality_score, reverse=True)

    source_counts = {}
    for a in all_articles:
        source_counts[a.source] = source_counts.get(a.source, 0) + 1
    logger.info(f"Total unique articles: {len(all_articles)}")
    logger.info(f"Source breakdown: {source_counts}")
    return all_articles
