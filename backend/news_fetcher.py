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
from datetime import datetime, timezone
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
    "platform engineering", "developer platform", "AI tooling", "AI SDK"
]

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
                    content=hit.get("story_text", "") or "",
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
    """Fetch latest AI papers from arXiv"""
    articles = []
    try:
        query = "all:LLM+OR+all:large+language+model+OR+all:AI+agent+OR+all:foundation+model"
        url = f"https://export.arxiv.org/api/query"
        params = {
            "search_query": query,
            "sortBy": "lastUpdatedDate",
            "sortOrder": "descending",
            "max_results": 20,
        }
        async with session.get(url, params=params) as resp:
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
            title = item.get("title", "") or ""
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
                content=desc,
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
    "https://medium.com/feed/tag/machine-learning",
    "https://medium.com/feed/tag/platform-engineering",
    "https://medium.com/feed/tag/mlops",
]

async def fetch_medium(session: aiohttp.ClientSession) -> List[RawArticle]:
    """Fetch AI articles from Medium RSS feeds"""
    articles = []
    for feed_url in MEDIUM_FEEDS:
        try:
            # Use rss2json proxy (free, no auth needed)
            proxy = f"https://api.rss2json.com/v1/api.json?rss_url={feed_url}&count=10"
            async with session.get(proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
            
            for item in data.get("items", []):
                title = item.get("title", "")
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
                    content=item.get("description", "")[:500],
                    author=item.get("author", ""),
                    tags=["medium"],
                    score=0
                ))
        except Exception as e:
            logger.warning(f"Medium feed {feed_url} error: {e}")
    
    logger.info(f"Medium: {len(articles)} articles")
    return articles


# ─────────────────────────────────────────────
# MAIN AGGREGATOR
# ─────────────────────────────────────────────
async def fetch_all_news() -> List[RawArticle]:
    """Fetch from all sources concurrently"""
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=20)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        results = await asyncio.gather(
            fetch_hackernews(session),
            fetch_arxiv(session),
            fetch_newsapi(session),
            fetch_medium(session),
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
    
    # Sort by score/recency
    all_articles.sort(key=lambda a: (a.score, a.published_at), reverse=True)
    logger.info(f"Total unique articles: {len(all_articles)}")
    return all_articles
