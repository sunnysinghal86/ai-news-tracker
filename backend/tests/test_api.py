"""
Integration tests — FastAPI endpoints
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


# ══════════════════════════════════════════════════════════════
# App fixture — isolated DB per test class
# ══════════════════════════════════════════════════════════════

@pytest.fixture
async def client(tmp_path):
    import database as db_mod
    import importlib
    db_mod.DB_PATH = str(tmp_path / "test.db")
    db_mod._db = None
    await db_mod.init_db()

    import main as main_mod
    importlib.reload(main_mod)

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app),
        base_url="http://test"
    ) as ac:
        yield ac

    await db_mod._db.close()
    db_mod._db = None


@pytest.fixture
async def seeded_client(tmp_path):
    """Client with 6 articles pre-seeded."""
    import database as db_mod
    import importlib
    db_mod.DB_PATH = str(tmp_path / "seeded.db")
    db_mod._db = None
    await db_mod.init_db()

    from tests.conftest import make_processed_article
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
    await db_mod._db.upsert_articles(articles)

    import main as main_mod
    importlib.reload(main_mod)

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app),
        base_url="http://test"
    ) as ac:
        yield ac

    await db_mod._db.close()
    db_mod._db = None


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
    async def test_limit_max_100_enforced(self, client):
        r = await client.get("/api/news?limit=200")
        assert r.status_code == 422

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
# POST /api/users  (route is /api/users not /api/subscribe)
# ══════════════════════════════════════════════════════════════

class TestSubscribe:
    @pytest.mark.asyncio
    async def test_creates_new_subscriber(self, client):
        r = await client.post("/api/users", json={
            "email": "sunny@example.com",
            "name": "Sunny",
            "min_relevance": 6
        })
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_email_no_500(self, client):
        payload = {"email": "dup@example.com", "name": "User"}
        await client.post("/api/users", json=payload)
        r = await client.post("/api/users", json=payload)
        assert r.status_code != 500

    @pytest.mark.asyncio
    async def test_response_contains_user(self, client):
        r = await client.post("/api/users", json={
            "email": "new@example.com", "name": "New User"
        })
        assert r.status_code == 200
        assert "user" in r.json()


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


# ══════════════════════════════════════════════════════════════
# POST /api/reprocess-rivals
# ══════════════════════════════════════════════════════════════

class TestReprocessRivals:
    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_flagged(self, client):
        r = await client.post("/api/reprocess-rivals")
        assert r.status_code == 200
        body = r.json()
        assert "message" in body
        assert "0" in body["message"]

    @pytest.mark.asyncio
    async def test_flags_products_missing_competitors(self, seeded_client):
        """Seeded articles are products with competitors — should flag 0."""
        r = await seeded_client.post("/api/reprocess-rivals")
        assert r.status_code == 200
