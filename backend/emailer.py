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

# Keys read fresh on every call — never cached at import time


def build_html_email(user_name: str, articles: List[dict]) -> str:
    """Generate beautiful HTML email digest"""
    app_url  = os.getenv("APP_URL", "https://ai-signal-frontend.onrender.com")
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
      <a href="{app_url}" style="color:#3b82f6;font-size:12px;text-decoration:none;">View Dashboard</a>
      &nbsp;·&nbsp;
      <a href="{app_url}/unsubscribe" style="color:#9ca3af;font-size:12px;text-decoration:none;">Unsubscribe</a>
    </div>
  </div>
</body>
</html>"""


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send email via Resend API"""
    # Read fresh on every call — not cached at import time
    api_key  = os.getenv("RESEND_API_KEY", "")
    from_email = os.getenv("FROM_EMAIL", "AI Signal <onboarding@resend.dev>")
    
    if not api_key:
        logger.error("RESEND_API_KEY not set in environment variables")
        return False
    
    logger.info(f"Sending via Resend — key prefix: {api_key[:8]}... from: {from_email}")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_body
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
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
    """Send daily digest to a user. Articles are pre-filtered by caller."""
    if not articles:
        logger.info(f"No articles to send to {user.email}")
        return False
    
    date_str = datetime.now().strftime("%b %d, %Y")
    subject = f"🤖 AI News Digest – {date_str} ({len(articles)} stories)"
    
    html = build_html_email(user.name or "there", articles)
    return await send_email(user.email, subject, html)


async def send_approval_request(
    subscriber_email: str,
    subscriber_name: str,
    approval_token: str,
) -> bool:
    """
    Send admin an approval/reject email when someone new subscribes.
    Admin email is read from ADMIN_EMAIL env var.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "")
    app_url     = os.getenv("APP_URL", "https://ai-signal.app")

    if not admin_email:
        logger.error("ADMIN_EMAIL not set — cannot send approval request")
        return False

    approve_url = f"{app_url}/api/users/approve?token={approval_token}"
    reject_url  = f"{app_url}/api/users/reject?token={approval_token}"

    from datetime import datetime as _dt
    requested_at = _dt.utcnow().strftime("%b %d, %Y at %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f5; margin: 0; padding: 40px 20px; }}
  .card {{ background: #fff; border-radius: 12px; max-width: 480px;
           margin: 0 auto; padding: 36px;
           box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
  .label {{ font-size: 11px; font-weight: 700; letter-spacing: 2px;
            text-transform: uppercase; color: #888; margin-bottom: 20px; }}
  h2 {{ font-size: 22px; font-weight: 700; color: #111; margin: 0 0 8px; }}
  .sub {{ background: #f8f8f8; border-radius: 8px; padding: 16px; margin: 20px 0; }}
  .sub p {{ margin: 5px 0; font-size: 14px; color: #444; }}
  .actions {{ display: flex; gap: 12px; margin-top: 28px; }}
  .btn {{ flex: 1; padding: 14px; border-radius: 8px; text-align: center;
          font-size: 15px; font-weight: 600; text-decoration: none; display: block; }}
  .approve {{ background: #16a34a; color: #fff; }}
  .reject  {{ background: #f5f5f5; color: #ef4444;
              border: 1.5px solid #fca5a5; }}
  .footer {{ margin-top: 24px; font-size: 12px; color: #bbb; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="label">AI Signal · New Subscription Request</div>
  <h2>Someone wants to subscribe 📬</h2>
  <p style="color:#555;font-size:15px;margin:4px 0 0">
    Review and approve or reject with one click.
  </p>
  <div class="sub">
    <p><strong>Name:</strong> {subscriber_name}</p>
    <p><strong>Email:</strong> {subscriber_email}</p>
    <p><strong>Requested:</strong> {requested_at}</p>
  </div>
  <div class="actions">
    <a href="{approve_url}" class="btn approve">✅ Approve</a>
    <a href="{reject_url}"  class="btn reject">❌ Reject</a>
  </div>
  <div class="footer">
    Single-use links · AI Signal ·
    <a href="{app_url}" style="color:#bbb;">ai-signal.app</a>
  </div>
</div>
</body>
</html>"""

    return await send_email(
        to_email=admin_email,
        subject=f"🔔 AI Signal — Approve {subscriber_name} ({subscriber_email})?",
        html_body=html,
    )
