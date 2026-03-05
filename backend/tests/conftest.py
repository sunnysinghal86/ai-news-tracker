"""
Shared pytest fixtures for AI Signal test suite.
"""

import pytest
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_fetcher import RawArticle
from summarizer import ProcessedArticle


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db(tmp_path):
    """Fresh isolated database per test using init_db() global pattern."""
    import database as db_mod
    db_mod.DB_PATH = str(tmp_path / "test.db")
    db_mod._db = None
    await db_mod.init_db()
    yield db_mod._db
    await db_mod._db.disconnect()   # actual method name
    db_mod._db = None


def make_raw_article(
    url="https://example.com/article-1",
    title="LangChain Launches Agent Memory Framework",
    source="Hacker News",
    content="LangChain has launched a new agent memory framework...",
    score=250,
) -> RawArticle:
    return RawArticle(
        id=url[-12:].replace("/", "_"),
        title=title,
        url=url,
        source=source,
        published_at=datetime.now(timezone.utc),
        content=content,
        author="test_author",
        tags=["AI", "LangChain"],
        score=score,
    )


def make_processed_article(
    id="abc123def456",
    title="LangChain Launches Agent Memory Framework",
    url="https://example.com/article-1",
    source="Hacker News",
    summary="LangChain v0.3 introduces persistent agent memory.",
    category="Product/Tool",
    relevance_score=9,
    is_product_or_tool=True,
    competitors=None,
    competitive_advantage="Native memory without Pinecone/Chroma dependency",
    published_at=None,
) -> ProcessedArticle:
    return ProcessedArticle(
        id=id,
        title=title,
        url=url,
        source=source,
        published_at=published_at or datetime.now(timezone.utc).isoformat(),
        author="test_author",
        score=250,
        summary=summary,
        category=category,
        tags=["AI", "LangChain", "memory"],
        relevance_score=relevance_score,
        is_product_or_tool=is_product_or_tool,
        product_name="LangChain" if is_product_or_tool else "",
        competitors=competitors if competitors is not None else [
            {"name": "LlamaIndex", "description": "RAG framework", "comparison": "LangChain has native memory"},
            {"name": "AutoGen", "description": "Multi-agent framework", "comparison": "Simpler memory API"},
        ],
        competitive_advantage=competitive_advantage,
    )


def make_user(
    email="test@example.com",
    name="Test User",
    categories=None,
    min_relevance=5,
):
    user = MagicMock()
    user.email = email
    user.name = name
    user.categories = categories
    user.min_relevance = min_relevance
    user.active = True
    return user
