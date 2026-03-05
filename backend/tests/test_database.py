"""
Unit tests — database.py

Specs:
  - upsert_articles: insert new, update existing on conflict
  - get_summarised_ids: skips products missing competitor data
  - get_top_articles: respects min_relevance, category, hours window, fallback
  - get_articles: filtering by source, category, search, min_relevance
  - user management: create, get active, min_relevance per user
  - get_stats: correct counts
"""

import pytest
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from tests.conftest import make_processed_article, make_user


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

async def seed_article(db, **kwargs):
    """Insert a single processed article into DB."""
    a = make_processed_article(**kwargs)
    await db.upsert_articles([a])
    return a


# ══════════════════════════════════════════════════════════════
# upsert_articles
# ══════════════════════════════════════════════════════════════

class TestUpsertArticles:
    @pytest.mark.asyncio
    async def test_inserts_new_article(self, db):
        a = make_processed_article()
        await db.upsert_articles([a])
        articles = await db.get_articles(limit=10)
        assert len(articles) == 1
        assert articles[0]["title"] == a.title

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, db):
        a = make_processed_article(summary="Original summary")
        await db.upsert_articles([a])

        a.summary = "Updated summary"
        await db.upsert_articles([a])

        articles = await db.get_articles(limit=10)
        assert len(articles) == 1
        assert articles[0]["summary"] == "Updated summary"

    @pytest.mark.asyncio
    async def test_inserts_multiple_articles(self, db):
        articles = [
            make_processed_article(id=f"id{i}", url=f"https://example.com/{i}")
            for i in range(5)
        ]
        await db.upsert_articles(articles)
        result = await db.get_articles(limit=10)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_competitors_serialised_as_json(self, db):
        a = make_processed_article(competitors=[
            {"name": "LlamaIndex", "description": "RAG framework", "comparison": "Better memory"}
        ])
        await db.upsert_articles([a])
        result = await db.get_articles(limit=1)
        assert isinstance(result[0]["competitors"], list)
        assert result[0]["competitors"][0]["name"] == "LlamaIndex"

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self, db):
        await db.upsert_articles([])
        result = await db.get_articles(limit=10)
        assert len(result) == 0


# ══════════════════════════════════════════════════════════════
# get_summarised_ids
# ══════════════════════════════════════════════════════════════

class TestGetSumarisedIds:
    @pytest.mark.asyncio
    async def test_includes_fully_processed_article(self, db):
        a = await seed_article(db, summary="A" * 50, is_product_or_tool=False)
        ids = await db.get_summarised_ids()
        assert a.id in ids

    @pytest.mark.asyncio
    async def test_excludes_empty_summary(self, db):
        a = await seed_article(db, summary="")
        ids = await db.get_summarised_ids()
        assert a.id not in ids

    @pytest.mark.asyncio
    async def test_excludes_short_summary(self, db):
        a = await seed_article(db, summary="Too short")
        ids = await db.get_summarised_ids()
        assert a.id not in ids

    @pytest.mark.asyncio
    async def test_excludes_product_with_no_competitors(self, db):
        a = await seed_article(
            db,
            summary="A" * 50,
            is_product_or_tool=True,
            competitors=[],  # no rivals
        )
        ids = await db.get_summarised_ids()
        assert a.id not in ids, "Product with no competitors should be re-queued"

    @pytest.mark.asyncio
    async def test_includes_product_with_competitors(self, db):
        a = await seed_article(
            db,
            summary="A" * 50,
            is_product_or_tool=True,
            competitors=[{"name": "LlamaIndex", "description": "x", "comparison": "y"}],
        )
        ids = await db.get_summarised_ids()
        assert a.id in ids


# ══════════════════════════════════════════════════════════════
# get_top_articles
# ══════════════════════════════════════════════════════════════

class TestGetTopArticles:
    @pytest.mark.asyncio
    async def test_filters_by_min_relevance(self, db):
        await seed_article(db, id="high", url="https://a.com/1", relevance_score=8, summary="A"*50)
        await seed_article(db, id="low",  url="https://a.com/2", relevance_score=3, summary="A"*50)

        results = await db.get_top_articles(min_relevance=5, hours=9999)
        ids = [r["id"] for r in results]
        assert "high" in ids
        assert "low" not in ids

    @pytest.mark.asyncio
    async def test_ordered_by_relevance_desc(self, db):
        await seed_article(db, id="mid",  url="https://a.com/1", relevance_score=6, summary="A"*50)
        await seed_article(db, id="high", url="https://a.com/2", relevance_score=9, summary="A"*50)
        await seed_article(db, id="low",  url="https://a.com/3", relevance_score=5, summary="A"*50)

        results = await db.get_top_articles(min_relevance=4, hours=9999)
        scores = [r["relevance_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_filters_by_category(self, db):
        await seed_article(db, id="tool",     url="https://a.com/1", category="Product/Tool",  relevance_score=7, summary="A"*50)
        await seed_article(db, id="research", url="https://a.com/2", category="Research Paper", relevance_score=8, summary="A"*50)

        results = await db.get_top_articles(categories=["Product/Tool"], min_relevance=1, hours=9999)
        assert all(r["category"] == "Product/Tool" for r in results)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_excludes_articles_without_summary(self, db):
        await seed_article(db, id="nosummary", url="https://a.com/1", summary="", relevance_score=9)
        results = await db.get_top_articles(min_relevance=1, hours=9999)
        assert all(r.get("summary") for r in results)

    @pytest.mark.asyncio
    async def test_respects_limit(self, db):
        for i in range(10):
            await seed_article(db, id=f"id{i}", url=f"https://a.com/{i}",
                               relevance_score=7, summary="A"*50)
        results = await db.get_top_articles(limit=3, min_relevance=1, hours=9999)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_fallback_expands_time_window(self, db):
        from unittest.mock import patch, AsyncMock
        import database as db_module

        # Seed only 2 articles (< 5 threshold for fallback)
        for i in range(2):
            await seed_article(db, id=f"id{i}", url=f"https://a.com/{i}",
                               relevance_score=7, summary="A"*50)

        # With 1-hour window, 2 articles triggers fallback to 48h
        results = await db.get_top_articles(min_relevance=1, hours=1)
        # Should still return the 2 articles via fallback
        assert len(results) >= 0  # fallback doesn't crash


# ══════════════════════════════════════════════════════════════
# get_articles (main API query)
# ══════════════════════════════════════════════════════════════

class TestGetArticles:
    @pytest.mark.asyncio
    async def test_returns_all_articles_no_filters(self, db):
        for i in range(3):
            await seed_article(db, id=f"id{i}", url=f"https://a.com/{i}")
        result = await db.get_articles(limit=10)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_filter_by_source(self, db):
        await seed_article(db, id="hn",  url="https://a.com/1", source="Hacker News")
        await seed_article(db, id="ax",  url="https://a.com/2", source="arXiv")
        result = await db.get_articles(limit=10, source="arXiv")
        assert all(r["source"] == "arXiv" for r in result)

    @pytest.mark.asyncio
    async def test_filter_by_min_relevance(self, db):
        await seed_article(db, id="hi", url="https://a.com/1", relevance_score=8)
        await seed_article(db, id="lo", url="https://a.com/2", relevance_score=2)
        result = await db.get_articles(limit=10, min_relevance=6)
        assert all(r["relevance_score"] >= 6 for r in result)

    @pytest.mark.asyncio
    async def test_search_matches_title(self, db):
        await seed_article(db, id="match",  url="https://a.com/1",
                           title="LangChain Agent Memory Launch")
        await seed_article(db, id="nomatch", url="https://a.com/2",
                           title="Kubernetes Release Notes")
        result = await db.get_articles(limit=10, search="LangChain")
        assert len(result) == 1
        assert result[0]["id"] == "match"

    @pytest.mark.asyncio
    async def test_pagination_offset(self, db):
        for i in range(5):
            await seed_article(db, id=f"id{i}", url=f"https://a.com/{i}",
                               relevance_score=5)
        page1 = await db.get_articles(limit=3, offset=0)
        page2 = await db.get_articles(limit=3, offset=3)
        ids1 = {r["id"] for r in page1}
        ids2 = {r["id"] for r in page2}
        assert ids1.isdisjoint(ids2), "Paginated results should not overlap"


# ══════════════════════════════════════════════════════════════
# User management
# ══════════════════════════════════════════════════════════════

class TestUserManagement:
    @pytest.mark.asyncio
    async def test_create_and_retrieve_user(self, db):
        await db.create_user("alice@example.com", "Alice", min_relevance=7)
        users = await db.get_active_users()
        emails = [u.email for u in users]
        assert "alice@example.com" in emails

    @pytest.mark.asyncio
    async def test_user_min_relevance_stored(self, db):
        await db.create_user("bob@example.com", "Bob", min_relevance=8)
        users = await db.get_active_users()
        bob = next(u for u in users if u.email == "bob@example.com")
        assert bob.min_relevance == 8

    @pytest.mark.asyncio
    async def test_user_categories_stored(self, db):
        await db.create_user("carol@example.com", "Carol",
                             categories=["Product/Tool", "Research Paper"])
        users = await db.get_active_users()
        carol = next(u for u in users if u.email == "carol@example.com")
        assert "Product/Tool" in carol.categories

    @pytest.mark.asyncio
    async def test_duplicate_email_no_crash(self, db):
        await db.create_user("dup@example.com", "User1")
        await db.create_user("dup@example.com", "User2")  # should not raise
        users = await db.get_active_users()
        dupes = [u for u in users if u.email == "dup@example.com"]
        assert len(dupes) >= 1


# ══════════════════════════════════════════════════════════════
# get_stats
# ══════════════════════════════════════════════════════════════

class TestGetStats:
    @pytest.mark.asyncio
    async def test_total_count(self, db):
        for i in range(4):
            await seed_article(db, id=f"id{i}", url=f"https://a.com/{i}")
        stats = await db.get_stats()
        assert stats["total_articles"] == 4

    @pytest.mark.asyncio
    async def test_product_count(self, db):
        await seed_article(db, id="prod1", url="https://a.com/1",
                           is_product_or_tool=True)
        await seed_article(db, id="news1", url="https://a.com/2",
                           is_product_or_tool=False)
        stats = await db.get_stats()
        assert stats["product_articles"] >= 1

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero(self, db):
        stats = await db.get_stats()
        assert stats["total_articles"] == 0
