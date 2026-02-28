"""
Email Service using Resend (free: 3000 emails/month, 100/day)
Sends beautifully formatted HTML daily digests
"""

import os
import aiohttp
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "AI News Tracker <digest@yourdomain.com>")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")


def build_html_email(user_name: str, articles: List[dict]) -> str:
    """Generate beautiful HTML email digest"""
    
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    
    # Group by category
    by_category = {}
    for a in articles:
        cat = a.get("category", "Industry News")
        by_category.setdefault(cat, []).append(a)
    
    # Build article cards
    def relevance_bar(score):
        filled = "●" * score + "○" * (10 - score)
        return filled
    
    def competitor_html(article):
        competitors = article.get("competitors", [])
        if not competitors or not article.get("is_product_or_tool"):
            return ""
        
        rows = ""
        for c in competitors[:3]:
            rows += f"""
            <tr>
              <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;font-weight:600;color:#1a1a2e;font-size:13px;">{c.get('name','')}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;color:#555;font-size:12px;">{c.get('description','')}</td>
              <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;color:#2d6a4f;font-size:12px;">{c.get('comparison','')}</td>
            </tr>"""
        
        adv = article.get("competitive_advantage", "")
        adv_html = f"""<div style="margin-top:8px;padding:8px 12px;background:#f0fdf4;border-left:3px solid #22c55e;border-radius:0 6px 6px 0;font-size:12px;color:#166534;"><strong>🏆 Key Advantage:</strong> {adv}</div>""" if adv else ""
        
        return f"""
        <div style="margin-top:12px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
          <div style="background:#f8f9fa;padding:8px 12px;font-size:11px;font-weight:700;color:#6b7280;letter-spacing:0.05em;text-transform:uppercase;">⚔️ Competitor Analysis</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
            <thead>
              <tr style="background:#fafafa;">
                <th style="padding:6px 8px;text-align:left;font-size:11px;color:#9ca3af;font-weight:600;">Competitor</th>
                <th style="padding:6px 8px;text-align:left;font-size:11px;color:#9ca3af;font-weight:600;">About</th>
                <th style="padding:6px 8px;text-align:left;font-size:11px;color:#9ca3af;font-weight:600;">How This Differs</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          {adv_html}
        </div>"""
    
    def article_card(a):
        rel_score = a.get("relevance_score", 5)
        rel_color = "#22c55e" if rel_score >= 7 else "#f59e0b" if rel_score >= 5 else "#9ca3af"
        tags = a.get("tags", [])[:3]
        tag_html = " ".join([f'<span style="display:inline-block;padding:2px 8px;background:#f3f4f6;border-radius:99px;font-size:10px;color:#6b7280;margin-right:4px;">{t}</span>' for t in tags])
        
        source_badge_colors = {
            "Hacker News": "#ff6600", "arXiv": "#b31b1b",
            "Medium": "#000000", "NewsAPI": "#2563eb"
        }
        source = a.get("source", "")
        src_key = next((k for k in source_badge_colors if k in source), "NewsAPI")
        src_color = source_badge_colors.get(src_key, "#6b7280")
        
        comp_html = competitor_html(a)
        
        return f"""
        <div style="margin-bottom:20px;padding:18px;background:#fff;border-radius:10px;border:1px solid #e5e7eb;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
            <span style="display:inline-block;padding:2px 10px;background:{src_color};color:#fff;border-radius:99px;font-size:11px;font-weight:600;">{a.get('source','')}</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:11px;color:{rel_color};font-weight:600;">Relevance: {rel_score}/10</span>
              {f'<span style="display:inline-block;padding:2px 8px;background:#dbeafe;color:#1d4ed8;border-radius:99px;font-size:10px;font-weight:600;">🔧 {a.get("category","")}</span>' if a.get("is_product_or_tool") else ''}
            </div>
          </div>
          <h3 style="margin:0 0 8px;font-size:16px;font-weight:700;line-height:1.4;">
            <a href="{a.get('url','#')}" style="color:#1a1a2e;text-decoration:none;">{a.get('title','')}</a>
          </h3>
          <p style="margin:0 0 10px;color:#555;font-size:14px;line-height:1.6;">{a.get('summary','No summary available.')}</p>
          <div>{tag_html}</div>
          {comp_html}
        </div>"""
    
    # Build section HTML
    sections_html = ""
    cat_icons = {
        "Product/Tool": "🔧", "AI Model": "🤖", "Research Paper": "📄",
        "Industry News": "📰", "Tutorial/Guide": "📚", "Platform/Infrastructure": "🏗️"
    }
    for cat, arts in by_category.items():
        icon = cat_icons.get(cat, "📌")
        cards = "\n".join([article_card(a) for a in arts])
        sections_html += f"""
        <div style="margin-bottom:32px;">
          <h2 style="margin:0 0 16px;font-size:14px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;border-bottom:2px solid #f3f4f6;padding-bottom:8px;">
            {icon} {cat} <span style="color:#d1d5db;font-weight:400;">({len(arts)})</span>
          </h2>
          {cards}
        </div>"""
    
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8f9fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:680px;margin:0 auto;padding:32px 16px;">
    
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);border-radius:14px;padding:32px;margin-bottom:24px;text-align:center;">
      <div style="font-size:32px;margin-bottom:8px;">🤖</div>
      <h1 style="margin:0 0 4px;font-size:24px;font-weight:800;color:#fff;letter-spacing:-0.5px;">AI News Tracker</h1>
      <p style="margin:0;color:#94a3b8;font-size:14px;">Daily Digest · {date_str}</p>
      <div style="margin-top:16px;padding:12px 20px;background:rgba(255,255,255,0.1);border-radius:8px;display:inline-block;">
        <span style="color:#e2e8f0;font-size:13px;">Hi {user_name} 👋 &nbsp;·&nbsp; </span>
        <span style="color:#60a5fa;font-size:13px;font-weight:600;">{len(articles)} top articles curated for you</span>
      </div>
    </div>
    
    <!-- Focus Banner -->
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;margin-bottom:24px;display:flex;align-items:center;gap:12px;">
      <span style="font-size:20px;">🎯</span>
      <div>
        <div style="font-weight:700;font-size:13px;color:#1a1a2e;">Focus: Software Development &amp; Platform Engineering</div>
        <div style="font-size:12px;color:#9ca3af;margin-top:2px;">Filtered for DevEx, MLOps, AI tooling, infrastructure &amp; developer platforms</div>
      </div>
    </div>
    
    <!-- Articles -->
    {sections_html}
    
    <!-- Footer -->
    <div style="text-align:center;padding:24px 0;border-top:1px solid #e5e7eb;margin-top:16px;">
      <p style="margin:0 0 8px;color:#9ca3af;font-size:12px;">You're receiving this because you subscribed to AI News Tracker.</p>
      <a href="{APP_URL}" style="color:#3b82f6;font-size:12px;text-decoration:none;">View Dashboard</a>
      &nbsp;·&nbsp;
      <a href="{APP_URL}/unsubscribe" style="color:#9ca3af;font-size:12px;text-decoration:none;">Unsubscribe</a>
    </div>
  </div>
</body>
</html>"""


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send email via Resend API"""
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set")
        return False
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html_body
            }
            headers = {
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            }
            async with session.post("https://api.resend.com/emails", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Email sent to {to_email}")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"Resend error {resp.status}: {body}")
                    return False
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


async def send_daily_digest(user, articles: List[dict]) -> bool:
    """Send daily digest to a user"""
    if not articles:
        logger.info(f"No articles to send to {user.email}")
        return False
    
    # Filter by user preferences
    filtered = articles
    if user.categories:
        filtered = [a for a in articles if a.get("category") in user.categories]
    if user.min_relevance:
        filtered = [a for a in filtered if a.get("relevance_score", 0) >= user.min_relevance]
    
    if not filtered:
        filtered = articles[:5]  # fallback
    
    date_str = datetime.now().strftime("%b %d, %Y")
    subject = f"🤖 AI News Digest – {date_str} ({len(filtered)} stories)"
    
    html = build_html_email(user.name or "there", filtered)
    return await send_email(user.email, subject, html)
