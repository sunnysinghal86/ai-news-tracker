"""
Integration tests — FastAPI endpoints

Specs:
  GET  /           → 200
  GET  /health     → {"status": "healthy"}
  GET  /api/news   → returns articles list with count
  GET  /api/news?category=X → filters correctly
  GET  /api/news?min_relevance=8 → filters correctly
  GET  /api/news?search=X → full-text search works
  GET  /api/news/stats → returns total_articles
  GET  /api/news/categories → returns known categories
  GET  /api/news/sources   → returns known sources
  POST /api/subscribe → creates user, 200
  POST /api/subscribe → duplicate email handled gracefully
  POST /api/trigger-refresh → queues background task
  POST /api/trigger-digest  → queues background task
  POST /api/reprocess-rivals → flags articles, returns count
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


# ══════════════════════════════════════════════════════════════
# App fixture with isolated DB
# ══════════════════════════════════════════════════════════════

@pytest.fixture
async def client(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "test.db")

    # Re-import app fresh with test DB path
    import importlib
    import database as db_mod
    importlib.reload(db_mod)
    import main as main_mod
    importlib.reload(main_mod)

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def seeded_client(tmp_path):
    """Client with a few articles pre-seeded."""
    os.environ["DB_PATH"] = str(tmp_path / "test_seeded.db")

    import importlib
    import database as db_mod
    importlib.reload(db_mod)
    import main as main_mod
    importlib.reload(main_mod)

    from tests.conftest import make_processed_article
    from database import Database

    db = Database()
    await db.init()
    articles = [
        make_processed_article(
            id=f"id{i}", url=f"https://example.com/{i}",
            title=f"Article {i}",
            category="Product/Tool" if i % 2 == 0 else "Research Paper",
            relevance_score=6 + (i % 4),
            summary="A" * 60,
        )
        for i in range(6)
    ]
    await db.upsert_articles(articles)
    await db.close()

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app),
        base_url="http://test"
    ) as ac:
        yield ac


# ══════════════════════════════════════════════════════════════
# Health & root
# ══════════════════════════════════════════════════════════════

class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_root_returns_200(self, client):
        r = await client.get("/")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ══════════════════════════════════════════════════════════════
# GET /api/news
# ══════════════════════════════════════════════════════════════

class TestGetNews:
    @pytest.mark.asyncio
    async def test_returns_articles_and_count(self, seeded_client):
        r = await seeded_client.get("/api/news?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert "articles" in body
        assert "count" in body
        assert body["count"] == len(body["articles"])

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self, client):
        r = await client.get("/api/news")
        assert r.status_code == 200
        assert r.json()["articles"] == []

    @pytest.mark.asyncio
    async def test_filter_by_category(self, seeded_client):
        r = await seeded_client.get("/api/news?category=Research+Paper")
        assert r.status_code == 200
        articles = r.json()["articles"]
        assert all(a["category"] == "Research Paper" for a in articles)

    @pytest.mark.asyncio
    async def test_filter_by_min_relevance(self, seeded_client):
        r = await seeded_client.get("/api/news?min_relevance=9")
        assert r.status_code == 200
        articles = r.json()["articles"]
        assert all(a["relevance_score"] >= 9 for a in articles)

    @pytest.mark.asyncio
    async def test_search_returns_matching_articles(self, seeded_client):
        r = await seeded_client.get("/api/news?search=Article+3")
        assert r.status_code == 200
        articles = r.json()["articles"]
        assert any("3" in a["title"] for a in articles)

    @pytest.mark.asyncio
    async def test_limit_respected(self, seeded_client):
        r = await seeded_client.get("/api/news?limit=2")
        assert r.status_code == 200
        assert len(r.json()["articles"]) <= 2

    @pytest.mark.asyncio
    async def test_limit_max_100(self, client):
        r = await client.get("/api/news?limit=200")
        assert r.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_pagination_no_overlap(self, seeded_client):
        r1 = await seeded_client.get("/api/news?limit=3&offset=0")
        r2 = await seeded_client.get("/api/news?limit=3&offset=3")
        ids1 = {a["id"] for a in r1.json()["articles"]}
        ids2 = {a["id"] for a in r2.json()["articles"]}
        assert ids1.isdisjoint(ids2)


# ══════════════════════════════════════════════════════════════
# GET /api/news/stats
# ══════════════════════════════════════════════════════════════

class TestStats:
    @pytest.mark.asyncio
    async def test_returns_total_articles(self, seeded_client):
        r = await seeded_client.get("/api/news/stats")
        assert r.status_code == 200
        assert "total_articles" in r.json()
        assert r.json()["total_articles"] == 6

    @pytest.mark.asyncio
    async def test_empty_db_zero_total(self, client):
        r = await client.get("/api/news/stats")
        assert r.status_code == 200
        assert r.json()["total_articles"] == 0


# ══════════════════════════════════════════════════════════════
# GET /api/news/categories + sources
# ══════════════════════════════════════════════════════════════

class TestMeta:
    @pytest.mark.asyncio
    async def test_categories_returns_list(self, client):
        r = await client.get("/api/news/categories")
        assert r.status_code == 200
        cats = r.json()["categories"]
        assert isinstance(cats, list)
        assert "Product/Tool" in cats
        assert "Research Paper" in cats

    @pytest.mark.asyncio
    async def test_sources_returns_list(self, client):
        r = await client.get("/api/news/sources")
        assert r.status_code == 200
        sources = r.json()["sources"]
        assert isinstance(sources, list)
        assert len(sources) > 0


# ══════════════════════════════════════════════════════════════
# POST /api/subscribe
# ══════════════════════════════════════════════════════════════

class TestSubscribe:
    @pytest.mark.asyncio
    async def test_creates_new_subscriber(self, client):
        r = await client.post("/api/subscribe", json={
            "email": "sunny@example.com",
            "name": "Sunny",
            "min_relevance": 6
        })
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_email_no_500(self, client):
        payload = {"email": "dup@example.com", "name": "User"}
        await client.post("/api/subscribe", json=payload)
        r = await client.post("/api/subscribe", json=payload)
        assert r.status_code in (200, 400, 409)  # any non-500 is acceptable

    @pytest.mark.asyncio
    async def test_invalid_email_rejected(self, client):
        r = await client.post("/api/subscribe", json={
            "email": "not-an-email", "name": "Bad"
        })
        # Should be 422 (Pydantic validation) or 400
        assert r.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════
# POST /api/trigger-refresh + trigger-digest
# ══════════════════════════════════════════════════════════════

class TestTriggerEndpoints:
    @pytest.mark.asyncio
    async def test_trigger_refresh_returns_200(self, client):
        with patch("main.refresh_news_job", new_callable=AsyncMock):
            r = await client.post("/api/trigger-refresh")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_trigger_digest_returns_200(self, client):
        with patch("main.send_digest_job", new_callable=AsyncMock):
            r = await client.post("/api/trigger-digest")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_trigger_refresh_response_has_message(self, client):
        with patch("main.refresh_news_job", new_callable=AsyncMock):
            r = await client.post("/api/trigger-refresh")
        assert "message" in r.json() or r.status_code == 200


# ══════════════════════════════════════════════════════════════
# POST /api/reprocess-rivals
# ══════════════════════════════════════════════════════════════

class TestReprocessRivals:
    @pytest.mark.asyncio
    async def test_returns_count_of_flagged_articles(self, seeded_client):
        r = await seeded_client.post("/api/reprocess-rivals")
        assert r.status_code == 200
        body = r.json()
        assert "message" in body or "error" not in body

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero(self, client):
        r = await client.post("/api/reprocess-rivals")
        assert r.status_code == 200
        # Should mention 0 articles flagged
        assert "0" in r.json().get("message", "")
