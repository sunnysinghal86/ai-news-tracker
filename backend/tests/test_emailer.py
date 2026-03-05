"""
Unit tests — emailer.py

Specs:
  - send_email: reads RESEND_API_KEY fresh on every call (not cached at import)
  - send_email: returns False when no API key
  - send_email: returns True on 200, False on 401/422
  - send_daily_digest: returns False when articles list is empty
  - send_daily_digest: passes correct article count to subject line
  - build_html_email: includes article title and summary in output
  - build_html_email: handles articles with no competitors
  - build_html_email: includes subscriber name
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import make_processed_article, make_user


def make_article_dict(**kwargs) -> dict:
    a = make_processed_article(**kwargs)
    return {
        "id": a.id, "title": a.title, "url": a.url, "source": a.source,
        "summary": a.summary, "category": a.category,
        "relevance_score": a.relevance_score,
        "is_product_or_tool": a.is_product_or_tool,
        "competitors": a.competitors,
        "competitive_advantage": a.competitive_advantage,
        "published_at": a.published_at, "author": a.author,
    }


# ══════════════════════════════════════════════════════════════
# send_email — key freshness
# ══════════════════════════════════════════════════════════════

class TestSendEmail:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_api_key(self):
        from emailer import send_email
        with patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            result = await send_email("test@test.com", "Subject", "<p>Body</p>")
        assert result is False

    @pytest.mark.asyncio
    async def test_reads_api_key_fresh_not_cached(self):
        """Key must be read from env at call time, not at import time."""
        from emailer import send_email

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"id": "abc123"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_resp)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)

        # Set key AFTER import — should still work
        with patch.dict(os.environ, {"RESEND_API_KEY": "re_fresh_key_123",
                                      "FROM_EMAIL": "AI Signal <onboarding@resend.dev>"}), \
             patch("emailer.aiohttp.ClientSession", return_value=mock_session_instance):
            result = await send_email("test@test.com", "Subject", "<p>Body</p>")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_401(self):
        from emailer import send_email

        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value='{"error": "Unauthorized"}')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_bad_key"}), \
             patch("emailer.aiohttp.ClientSession", return_value=mock_session):
            result = await send_email("test@test.com", "Subject", "<p>Body</p>")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_exception(self):
        from emailer import send_email
        import aiohttp
        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test_key"}), \
             patch("emailer.aiohttp.ClientSession", side_effect=aiohttp.ClientError("timeout")):
            result = await send_email("test@test.com", "Subject", "<p>Body</p>")
        assert result is False


# ══════════════════════════════════════════════════════════════
# send_daily_digest
# ══════════════════════════════════════════════════════════════

class TestSendDailyDigest:
    @pytest.mark.asyncio
    async def test_returns_false_for_empty_articles(self):
        from emailer import send_daily_digest
        user = make_user()
        result = await send_daily_digest(user, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_calls_send_email_with_correct_count_in_subject(self):
        from emailer import send_daily_digest
        user = make_user(name="Sunny")
        articles = [make_article_dict() for _ in range(5)]

        with patch("emailer.send_email", new_callable=AsyncMock, return_value=True) as mock_send:
            await send_daily_digest(user, articles)

        assert mock_send.called
        subject = mock_send.call_args[0][1]
        assert "5" in subject

    @pytest.mark.asyncio
    async def test_sends_to_correct_email(self):
        from emailer import send_daily_digest
        user = make_user(email="sunny@example.com")
        articles = [make_article_dict()]

        with patch("emailer.send_email", new_callable=AsyncMock, return_value=True) as mock_send:
            await send_daily_digest(user, articles)

        assert mock_send.call_args[0][0] == "sunny@example.com"

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_send(self):
        from emailer import send_daily_digest
        user = make_user()
        articles = [make_article_dict()]

        with patch("emailer.send_email", new_callable=AsyncMock, return_value=True):
            result = await send_daily_digest(user, articles)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_send_fails(self):
        from emailer import send_daily_digest
        user = make_user()
        articles = [make_article_dict()]

        with patch("emailer.send_email", new_callable=AsyncMock, return_value=False):
            result = await send_daily_digest(user, articles)
        assert result is False


# ══════════════════════════════════════════════════════════════
# build_html_email
# ══════════════════════════════════════════════════════════════

class TestBuildHtmlEmail:
    def test_includes_subscriber_name(self):
        from emailer import build_html_email
        html = build_html_email("Sunny", [make_article_dict()])
        assert "Sunny" in html

    def test_includes_article_title(self):
        from emailer import build_html_email
        article = make_article_dict(title="LangChain v0.3 Launches Agent Memory")
        html = build_html_email("User", [article])
        assert "LangChain v0.3 Launches Agent Memory" in html

    def test_includes_article_summary(self):
        from emailer import build_html_email
        article = make_article_dict(summary="This is a very specific summary text.")
        html = build_html_email("User", [article])
        assert "This is a very specific summary text." in html

    def test_renders_without_competitors(self):
        from emailer import build_html_email
        article = make_article_dict(competitors=[], competitive_advantage="")
        # Should not raise
        html = build_html_email("User", [article])
        assert "<html" in html.lower() or "<!doctype" in html.lower() or "<div" in html.lower()

    def test_renders_multiple_articles(self):
        from emailer import build_html_email
        articles = [
            make_article_dict(id=f"id{i}", url=f"https://a.com/{i}",
                              title=f"Article Title {i}")
            for i in range(3)
        ]
        html = build_html_email("User", articles)
        assert "Article Title 0" in html
        assert "Article Title 1" in html
        assert "Article Title 2" in html

    def test_returns_string(self):
        from emailer import build_html_email
        html = build_html_email("User", [make_article_dict()])
        assert isinstance(html, str)
        assert len(html) > 100
