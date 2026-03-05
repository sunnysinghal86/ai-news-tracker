"""
Unit tests — summarizer.py
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from news_fetcher import RawArticle
from summarizer import ProcessedArticle
from tests.conftest import make_raw_article


# ══════════════════════════════════════════════════════════════
# _call_claude
# ══════════════════════════════════════════════════════════════

class TestCallClaude:
    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        from summarizer import _call_claude
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "content": [{"type": "text", "text": '{"summary": "test"}'}]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = await _call_claude("test prompt", mock_session)
        assert result == '{"summary": "test"}'

    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self):
        from summarizer import _call_claude
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            mock_session = MagicMock()
            result = await _call_claude("test", mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_429_then_returns_none(self):
        from summarizer import _call_claude
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.json = AsyncMock(return_value={"error": {"type": "rate_limit_error"}})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
             patch("summarizer.asyncio.sleep", new_callable=AsyncMock):
            result = await _call_claude("test", mock_session, retries=2)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_5xx_error(self):
        from summarizer import _call_claude
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.json = AsyncMock(return_value={"error": "service unavailable"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
             patch("summarizer.asyncio.sleep", new_callable=AsyncMock):
            result = await _call_claude("test", mock_session, retries=1)
        assert result is None


# ══════════════════════════════════════════════════════════════
# _analyse_article — JSON parsing
# ══════════════════════════════════════════════════════════════

class TestAnalyseArticle:
    @pytest.mark.asyncio
    async def test_parses_valid_response(self):
        from summarizer import _analyse_article
        article = make_raw_article()
        claude_json = json.dumps({
            "summary": "LangChain launches agent memory for stateful workflows.",
            "category": "Product/Tool",
            "tags": ["LangChain", "AI", "memory"],
            "relevance_score": 9,
            "is_product_or_tool": True,
            "product_name": "LangChain",
            "competitors": [
                {"name": "LlamaIndex", "description": "RAG", "comparison": "Simpler API"}
            ],
            "competitive_advantage": "No external vector store needed"
        })

        mock_session = MagicMock()
        with patch("summarizer._call_claude", new_callable=AsyncMock, return_value=claude_json):
            result = await _analyse_article(article, mock_session)

        assert result.summary == "LangChain launches agent memory for stateful workflows."
        assert result.category == "Product/Tool"
        assert result.relevance_score == 9
        assert result.is_product_or_tool is True
        assert result.product_name == "LangChain"
        assert len(result.competitors) == 1
        assert result.competitive_advantage == "No external vector store needed"

    @pytest.mark.asyncio
    async def test_defaults_on_malformed_json(self):
        from summarizer import _analyse_article
        article = make_raw_article()
        mock_session = MagicMock()
        with patch("summarizer._call_claude", new_callable=AsyncMock,
                   return_value="{ this is not valid json"):
            result = await _analyse_article(article, mock_session)
        assert isinstance(result, ProcessedArticle)
        assert result.id == article.id

    @pytest.mark.asyncio
    async def test_returns_processarticle_on_none_response(self):
        """When Claude returns None, article still returns as ProcessedArticle with content fallback."""
        from summarizer import _analyse_article
        article = make_raw_article(content="Some article content here")
        mock_session = MagicMock()
        with patch("summarizer._call_claude", new_callable=AsyncMock, return_value=None):
            result = await _analyse_article(article, mock_session)
        # Should return ProcessedArticle (not crash), summary may use content as fallback
        assert isinstance(result, ProcessedArticle)
        assert result.id == article.id

    @pytest.mark.asyncio
    async def test_missing_fields_use_defaults(self):
        from summarizer import _analyse_article
        article = make_raw_article()
        claude_json = json.dumps({"summary": "Minimal response only"})
        mock_session = MagicMock()
        with patch("summarizer._call_claude", new_callable=AsyncMock, return_value=claude_json):
            result = await _analyse_article(article, mock_session)
        assert result.summary == "Minimal response only"
        assert result.relevance_score == 5         # default
        assert result.is_product_or_tool is False   # default
        assert result.competitors == []             # default for non-product


# ══════════════════════════════════════════════════════════════
# _enrich_one — content enrichment
# ══════════════════════════════════════════════════════════════

class TestEnrichOne:
    @pytest.mark.asyncio
    async def test_skips_article_with_rich_content(self):
        """Articles with > 200 chars content are returned as-is."""
        from summarizer import _enrich_one
        article = make_raw_article(content="A" * 300)
        mock_session = MagicMock()
        result = await _enrich_one(article, mock_session)
        mock_session.get.assert_not_called()
        assert result.content == "A" * 300

    @pytest.mark.asyncio
    async def test_skips_hacker_news_urls(self):
        from summarizer import _enrich_one
        article = make_raw_article(url="https://news.ycombinator.com/item?id=12345", content="")
        mock_session = MagicMock()
        result = await _enrich_one(article, mock_session)
        mock_session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_paywalled_domains(self):
        from summarizer import _enrich_one
        for domain in ["wsj.com", "ft.com", "bloomberg.com", "nytimes.com", "economist.com"]:
            article = make_raw_article(url=f"https://www.{domain}/article", content="")
            mock_session = MagicMock()
            result = await _enrich_one(article, mock_session)
            mock_session.get.assert_not_called(), f"{domain} should be skipped"

    @pytest.mark.asyncio
    async def test_uses_trafilatura_when_available(self):
        from summarizer import _enrich_one
        article = make_raw_article(content="Short")
        rich_body = "Full article body with lots of real content. " * 20

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = AsyncMock(return_value="<html><body><p>" + rich_body + "</p></body></html>")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("summarizer.trafilatura.extract", return_value=rich_body):
            result = await _enrich_one(article, mock_session)

        assert len(result.content) > len("Short")

    @pytest.mark.asyncio
    async def test_falls_back_to_og_description(self):
        from summarizer import _enrich_one
        article = make_raw_article(content="")
        # Use attribute-before-content meta tag format that matches the regex
        html = '<html><head><meta property="og:description" content="Great article about AI agents"></head></html>'

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = AsyncMock(return_value=html)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        # trafilatura returns nothing (too short) → fallback to og:description
        with patch("summarizer.trafilatura.extract", return_value="short"):
            result = await _enrich_one(article, mock_session)

        assert "Great article about AI agents" in result.content

    @pytest.mark.asyncio
    async def test_handles_http_404_gracefully(self):
        from summarizer import _enrich_one
        article = make_raw_article(content="")
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        result = await _enrich_one(article, mock_session)
        assert result is not None  # should not raise

    @pytest.mark.asyncio
    async def test_handles_network_exception_gracefully(self):
        from summarizer import _enrich_one
        import aiohttp
        article = make_raw_article(content="")
        mock_session = MagicMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection refused")
        result = await _enrich_one(article, mock_session)
        assert result is not None


# ══════════════════════════════════════════════════════════════
# summarize_articles — orchestration
# ══════════════════════════════════════════════════════════════

class TestSummarizeArticles:
    @pytest.mark.asyncio
    async def test_caps_at_30_articles_when_key_set(self):
        """Cap at 30 only applies when ANTHROPIC_API_KEY is present."""
        from summarizer import summarize_articles
        articles = [make_raw_article(url=f"https://a.com/{i}") for i in range(50)]

        fake = ProcessedArticle(id="x", title="t", url="u", source="s",
                                published_at="2024-01-01", author="a", score=1)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
             patch("summarizer._analyse_article", new_callable=AsyncMock, return_value=fake), \
             patch("summarizer.enrich_all", new_callable=AsyncMock, return_value=articles[:30]), \
             patch("summarizer.asyncio.sleep", new_callable=AsyncMock):
            results = await summarize_articles(articles)

        assert len(results) <= 30

    @pytest.mark.asyncio
    async def test_no_key_returns_content_fallback_for_all(self):
        """Without API key, all articles get content-based fallback summaries."""
        from summarizer import summarize_articles
        articles = [make_raw_article(url=f"https://a.com/{i}", content="x"*50) for i in range(5)]

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            results = await summarize_articles(articles)

        assert len(results) == 5
        assert all(isinstance(r, ProcessedArticle) for r in results)

    @pytest.mark.asyncio
    async def test_content_cap_is_1200_chars_in_prompt(self):
        """Verify the prompt sends up to 1200 chars, not the old 600."""
        from summarizer import _analyse_article
        long_content = "X" * 2000
        article = make_raw_article(content=long_content)

        captured = []
        async def capture(prompt, session, **kwargs):
            captured.append(prompt)
            return None

        mock_session = MagicMock()
        with patch("summarizer._call_claude", side_effect=capture):
            await _analyse_article(article, mock_session)

        assert len(captured) == 1
        assert "X" * 1200 in captured[0]
        assert "X" * 1201 not in captured[0]
