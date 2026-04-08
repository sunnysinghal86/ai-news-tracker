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


def build_html_email(user_name, digest, unsubscribe_token=""):
    app_url = os.getenv("APP_URL", "https://ai-signal.app")
    api_url = os.getenv("API_URL", "https://api.ai-signal.app")
    date_str = datetime.now().strftime("%A, %B %d")
    stories = digest.get("stories", [])
    sleeper = digest.get("sleeper")
    trends  = digest.get("trends", [])
    total   = digest.get("article_count", len(stories))

    def score_dot(score):
        color = "#22c55e" if score >= 8 else "#f59e0b" if score >= 6 else "#9ca3af"
        return f'<span style="color:{color};font-weight:700;">{score}/10</span>'

    def source_chip(source):
        colors = {
            "Anthropic Blog": "#c17f2a", "OpenAI Blog": "#1a6b4a",
            "Google AI Blog": "#1a6b8a", "AWS AI Blog": "#8a3a00",
            "platformengineering.org": "#1c4d35", "Medium": "#1a1208",
            "NewsAPI": "#b5860d",
        }
        bg = colors.get(source, "#6b7280")
        return (f'<span style="display:inline-block;padding:2px 10px;background:{bg};'
                f'color:#fff;border-radius:4px;font-size:11px;font-weight:600;">{source}</span>')

    def story_card(a, index):
        is_lead  = index == 0 or a.get("is_lead", False)
        title    = a.get("title", "")
        url      = a.get("url", "#")
        summary  = a.get("summary", "")
        score    = a.get("relevance_score", 5)
        source   = a.get("source", "")
        impl     = a.get("implication", "")
        also     = a.get("also_covered_by", [])
        comp_adv = a.get("competitive_advantage", "")
        competitors = a.get("competitors", [])

        border  = "2px solid #1a1a2e" if is_lead else "1px solid #e5e7eb"
        padding = "22px" if is_lead else "16px"
        fsize   = "17px" if is_lead else "15px"

        comp_rows = "".join([
            f'<tr><td style="padding:5px 8px;font-weight:600;font-size:12px;">{c.get("name","")}</td>'
            f'<td style="padding:5px 8px;font-size:12px;color:#555;">{c.get("comparison","")}</td></tr>'
            for c in competitors[:3]
        ])
        comp_html = ""
        if competitors and a.get("is_product_or_tool"):
            edge = (f'<div style="padding:8px;background:#f0fdf4;font-size:12px;color:#166534;">'
                    f'<strong>Edge:</strong> {comp_adv}</div>') if comp_adv else ""
            comp_html = (
                f'<div style="margin-top:10px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">'
                f'<div style="background:#f8f9fa;padding:6px 10px;font-size:10px;font-weight:700;'
                f'color:#6b7280;text-transform:uppercase;">vs Competitors</div>'
                f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
                f'<thead><tr>'
                f'<th style="padding:5px 8px;font-size:10px;color:#9ca3af;text-align:left;">Name</th>'
                f'<th style="padding:5px 8px;font-size:10px;color:#9ca3af;text-align:left;">How this differs</th>'
                f'</tr></thead><tbody>{comp_rows}</tbody></table>{edge}</div>'
            )

        also_html = ""
        if also:
            links = " · ".join([f'<a href="{x["url"]}" style="color:#6b7280;font-size:11px;">{x["source"]}</a>' for x in also])
            also_html = f'<div style="margin-top:8px;font-size:11px;color:#9ca3af;">Also covered: {links}</div>'

        impl_html = ""
        if impl and impl != "N/A":
            impl_html = (f'<div style="margin-top:10px;padding:10px 14px;background:#eff6ff;'
                         f'border-left:3px solid #3b82f6;border-radius:0 6px 6px 0;'
                         f'font-size:12px;color:#1e40af;line-height:1.5;">&#x1F4A1; {impl}</div>')

        lead_label = ('<div style="margin-bottom:10px;"><span style="background:#1a1a2e;color:#fff;'
                      'font-size:10px;font-weight:700;padding:3px 10px;border-radius:4px;">'
                      'TOP STORY</span></div>') if is_lead else ""

        return (
            f'<div style="margin-bottom:14px;padding:{padding};background:#fff;'
            f'border:{border};border-radius:8px;">'
            f'{lead_label}'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">'
            f'{source_chip(source)} {score_dot(score)}'
            f'<span style="font-size:11px;color:#9ca3af;">{a.get("category","")}</span></div>'
            f'<h3 style="margin:0 0 8px;font-size:{fsize};font-weight:700;line-height:1.35;color:#1a1a2e;">'
            f'<a href="{url}" style="color:inherit;text-decoration:none;">{title}</a></h3>'
            f'<p style="margin:0;color:#555;font-size:13px;line-height:1.6;">{summary}</p>'
            f'{impl_html}{comp_html}{also_html}</div>'
        )

    stories_html = "".join([story_card(a, i) for i, a in enumerate(stories)])

    sleeper_html = ""
    if sleeper:
        sleeper_html = (
            '<div style="margin-top:28px;">'
            '<div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;'
            'letter-spacing:0.08em;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #f3f4f6;">'
            '&#x1F50D; Under the Radar</div>'
            + story_card(sleeper, 99) +
            '<p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">'
            'Lower scored but caught our eye &#8212; worth a read if you have time.</p></div>'
        )

    trends_html = ""
    if trends:
        chips = "".join([
            f'<span style="display:inline-block;margin:3px 4px 3px 0;padding:4px 12px;'
            f'background:#f3f4f6;border-radius:99px;font-size:12px;color:#374151;">'
            f'&#x1F4C8; {t}</span>'
            for t in trends
        ])
        trends_html = (
            '<div style="margin-top:28px;padding:16px 18px;background:#fafafa;'
            'border:1px solid #e5e7eb;border-radius:8px;">'
            '<div style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;'
            'letter-spacing:0.08em;margin-bottom:10px;">Recurring Themes (last 14 days)</div>'
            + chips + '</div>'
        )

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f8f9fa;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
        '<div style="max-width:660px;margin:0 auto;padding:28px 16px;">'
        '<div style="background:linear-gradient(135deg,#1a1a2e 0%,#0f3460 100%);'
        'border-radius:12px;padding:28px 32px;margin-bottom:20px;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;">'
        '<div><div style="font-size:20px;font-weight:800;color:#fff;">AI Signal</div>'
        f'<div style="color:#94a3b8;font-size:13px;margin-top:2px;">'
        f'{date_str} &nbsp;&#183;&nbsp; {total} stories for {user_name}</div></div>'
        f'<a href="{app_url}" style="color:#60a5fa;font-size:12px;text-decoration:none;">View feed &rarr;</a>'
        '</div></div>'
        + stories_html + sleeper_html + trends_html +
        f'<div style="text-align:center;padding:20px 0;margin-top:20px;border-top:1px solid #e5e7eb;">'
        f'<a href="{app_url}" style="color:#6b7280;font-size:12px;text-decoration:none;margin:0 8px;">Dashboard</a>'
        f' &nbsp;&#183;&nbsp; '
        f'<a href="{api_url}/api/users/unsubscribe?token={unsubscribe_token}" '
        f'style="color:#9ca3af;font-size:12px;text-decoration:none;margin:0 8px;">Unsubscribe</a>'
        f'</div></div></body></html>'
    )


async def send_daily_digest(user, digest: dict) -> bool:
    """Send curated editorial digest to a user."""
    if not digest.get("stories"):
        logger.info(f"Empty digest for {user.email} — skipping")
        return False
    date_str    = datetime.now().strftime("%b %d, %Y")
    total       = digest.get("article_count", 0)
    subject     = f"AI Signal \u00b7 {date_str} \u00b7 {total} stories worth reading"
    unsub_token = getattr(user, "unsubscribe_token", "") or ""
    html        = build_html_email(user.name or "there", digest, unsubscribe_token=unsub_token)
    return await send_email(user.email, subject, html)



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
    
    unsub_token = getattr(user, "unsubscribe_token", "") or ""
    html = build_html_email(user.name or "there", articles, unsubscribe_token=unsub_token)
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

    # Approve/reject endpoints are on the BACKEND (api.ai-signal.app)
    # APP_URL is the frontend — derive backend URL from it
    api_url = os.getenv("API_URL", app_url.replace("ai-signal.app", "api.ai-signal.app"))
    approve_url = f"{api_url}/api/users/approve?token={approval_token}"
    reject_url  = f"{api_url}/api/users/reject?token={approval_token}"

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


async def send_rejection_email(subscriber_email: str, subscriber_name: str) -> bool:
    """
    Notify a rejected subscriber politely.
    Sent automatically when admin clicks Reject in the approval email.
    """
    app_url = os.getenv("APP_URL", "https://ai-signal.app")

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
  h2 {{ font-size: 22px; font-weight: 700; color: #111; margin: 0 0 12px; }}
  p {{ color: #555; font-size: 15px; line-height: 1.6; margin: 0 0 16px; }}
  .footer {{ margin-top: 28px; font-size: 12px; color: #bbb; }}
</style>
</head>
<body>
<div class="card">
  <div class="label">AI Signal</div>
  <h2>Thanks for your interest, {subscriber_name}</h2>
  <p>
    We've reviewed your subscription request for the AI Signal daily digest
    and unfortunately we're not able to add you at this time.
  </p>
  <p>
    This may be because we're managing capacity or the digest isn't the right
    fit right now. You're welcome to browse the latest stories on the dashboard.
  </p>
  <a href="{app_url}" style="display:inline-block;margin-top:8px;
     padding:12px 24px;background:#111;color:#fff;border-radius:8px;
     text-decoration:none;font-weight:600;font-size:14px;">
    Browse AI Signal →
  </a>
  <div class="footer">AI Signal · {app_url}</div>
</div>
</body>
</html>"""

    return await send_email(
        to_email=subscriber_email,
        subject="AI Signal — Subscription Request Update",
        html_body=html,
    )
