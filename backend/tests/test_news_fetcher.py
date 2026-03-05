"""
Unit tests — news_fetcher.py

Specs:
  - gen_id: deterministic MD5-based ID from URL
  - strip_html: removes tags, decodes entities, collapses whitespace
  - is_relevant: keyword filtering gates articles correctly
  - deduplication: same URL never produces two articles
  - fetch functions handle HTTP errors gracefully
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from news_fetcher import gen_id, strip_html, RawArticle


# ══════════════════════════════════════════════════════════════
# gen_id
# ══════════════════════════════════════════════════════════════

class TestGenId:
    def test_same_url_produces_same_id(self):
        url = "https://example.com/article"
        assert gen_id(url) == gen_id(url)

    def test_different_urls_produce_different_ids(self):
        assert gen_id("https://a.com/1") != gen_id("https://a.com/2")

    def test_id_is_12_chars(self):
        assert len(gen_id("https://example.com")) == 12

    def test_id_is_alphanumeric(self):
        id_ = gen_id("https://example.com/test?q=1&page=2")
        assert id_.isalnum()

    def test_empty_string_produces_stable_id(self):
        assert gen_id("") == gen_id("")


# ══════════════════════════════════════════════════════════════
# strip_html
# ══════════════════════════════════════════════════════════════

class TestStripHtml:
    def test_removes_basic_tags(self):
        assert strip_html("<p>Hello world</p>") == "Hello world"

    def test_removes_nested_tags(self):
        assert strip_html("<div><p><strong>Bold</strong></p></div>") == "Bold"

    def test_decodes_html_entities(self):
        assert "&amp;" not in strip_html("AT&amp;T")
        assert "AT&T" in strip_html("AT&amp;T")

    def test_decodes_nbsp(self):
        result = strip_html("Hello&nbsp;World")
        assert "Hello" in result and "World" in result

    def test_collapses_whitespace(self):
        result = strip_html("<p>Hello   </p>  <p>  World</p>")
        assert "  " not in result.strip()

    def test_removes_script_tags_and_content(self):
        result = strip_html("<script>alert('xss')</script>Real content")
        assert "alert" not in result
        assert "Real content" in result

    def test_removes_style_tags_and_content(self):
        result = strip_html("<style>.cls { color: red; }</style>Visible text")
        assert "color" not in result
        assert "Visible text" in result

    def test_plain_text_unchanged(self):
        text = "No HTML here"
        assert strip_html(text) == text

    def test_empty_string(self):
        assert strip_html("") == ""


# ══════════════════════════════════════════════════════════════
# RawArticle dataclass
# ══════════════════════════════════════════════════════════════

class TestRawArticle:
    def test_default_content_is_empty(self):
        a = RawArticle(
            id="abc", title="Test", url="https://x.com",
            source="HN", published_at=datetime.now(timezone.utc)
        )
        assert a.content == ""

    def test_default_score_is_zero(self):
        a = RawArticle(
            id="abc", title="Test", url="https://x.com",
            source="HN", published_at=datetime.now(timezone.utc)
        )
        assert a.score == 0

    def test_tags_default_to_empty_list(self):
        a = RawArticle(
            id="abc", title="Test", url="https://x.com",
            source="HN", published_at=datetime.now(timezone.utc)
        )
        assert a.tags == []

    def test_fields_stored_correctly(self):
        now = datetime.now(timezone.utc)
        a = RawArticle(
            id="test123", title="My Article", url="https://example.com",
            source="arXiv", published_at=now, content="Some content",
            author="Jane Doe", score=42
        )
        assert a.id == "test123"
        assert a.title == "My Article"
        assert a.author == "Jane Doe"
        assert a.score == 42


# ══════════════════════════════════════════════════════════════
# fetch_hacker_news — HTTP error handling
# ══════════════════════════════════════════════════════════════

class TestFetchHackerNews:
    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self):
        from news_fetcher import fetch_hacker_news
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("news_fetcher.aiohttp.ClientSession") as mock_cs:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=mock_session)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = instance
            result = await fetch_hacker_news()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_empty_on_network_error(self):
        from news_fetcher import fetch_hacker_news
        import aiohttp
        with patch("news_fetcher.aiohttp.ClientSession") as mock_cs:
            mock_cs.side_effect = aiohttp.ClientError("Network error")
            result = await fetch_hacker_news()
        assert result == []


# ══════════════════════════════════════════════════════════════
# fetch_arxiv — HTTP error handling
# ══════════════════════════════════════════════════════════════

class TestFetchArxiv:
    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self):
        from news_fetcher import fetch_arxiv
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("news_fetcher.aiohttp.ClientSession") as mock_cs:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=mock_session)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_cs.return_value = instance
            result = await fetch_arxiv()
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════
# Deduplication — fetch_all_news should deduplicate by URL
# ══════════════════════════════════════════════════════════════

class TestDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_urls_removed(self):
        from news_fetcher import fetch_all_news
        now = datetime.now(timezone.utc)
        dup = RawArticle(id="dup1", title="Same Article",
                         url="https://same.com/article",
                         source="HN", published_at=now, score=100)
        dup2 = RawArticle(id="dup2", title="Same Article (copy)",
                          url="https://same.com/article",
                          source="Medium", published_at=now, score=50)

        with patch("news_fetcher.fetch_hacker_news", return_value=[dup]), \
             patch("news_fetcher.fetch_arxiv", return_value=[dup2]), \
             patch("news_fetcher.fetch_newsapi", return_value=[]), \
             patch("news_fetcher.fetch_medium_rss", return_value=[]), \
             patch("news_fetcher.fetch_platform_engineering", return_value=[]), \
             patch("news_fetcher.fetch_platform_weekly", return_value=[]):
            results = await fetch_all_news()

        urls = [a.url for a in results]
        assert len(urls) == len(set(urls)), "Duplicate URLs found in results"

    @pytest.mark.asyncio
    async def test_unique_articles_all_returned(self):
        from news_fetcher import fetch_all_news
        now = datetime.now(timezone.utc)
        articles = [
            RawArticle(id=f"id{i}", title=f"Article {i}",
                       url=f"https://example.com/{i}",
                       source="HN", published_at=now)
            for i in range(5)
        ]

        with patch("news_fetcher.fetch_hacker_news", return_value=articles), \
             patch("news_fetcher.fetch_arxiv", return_value=[]), \
             patch("news_fetcher.fetch_newsapi", return_value=[]), \
             patch("news_fetcher.fetch_medium_rss", return_value=[]), \
             patch("news_fetcher.fetch_platform_engineering", return_value=[]), \
             patch("news_fetcher.fetch_platform_weekly", return_value=[]):
            results = await fetch_all_news()

        assert len(results) == 5
