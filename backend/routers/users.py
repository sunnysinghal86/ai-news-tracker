"""
routers/users.py — updated with approval workflow

New endpoints:
  GET /api/users/approve?token=xxx  → approves subscriber, sends welcome email
  GET /api/users/reject?token=xxx   → rejects & deletes subscriber
  GET /api/users/pending            → list users awaiting approval (admin view)

Existing endpoints unchanged:
  GET    /api/users      → list active subscribers
  POST   /api/users      → subscribe (now triggers approval email to admin)
  DELETE /api/users/{email}
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from database import get_db
from emailer import send_approval_request, send_email, send_rejection_email
from typing import List, Optional
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class UserCreate(BaseModel):
    email: str
    name: str
    categories: Optional[List[str]] = []
    min_relevance: int = 5


# ── Subscribe (triggers approval flow) ───────────────────────────────────────

@router.post("")
async def create_user(data: UserCreate):
    """
    Subscribe to AI Signal digest.

    Creates user as active=0 (pending) and sends admin an approval email.
    User only receives digests after admin clicks Approve.
    """
    async with get_db() as db:
        user = await db.create_user(
            email=data.email,
            name=data.name,
            categories=data.categories,
            min_relevance=data.min_relevance,
            require_approval=True,   # active=0, generates token
        )

    if user and user.approval_token:
        # Send approval request to admin
        sent = await send_approval_request(
            subscriber_email=user.email,
            subscriber_name=user.name,
            approval_token=user.approval_token,
        )
        if sent:
            logger.info(f"Approval request sent to admin for: {user.email}")
        else:
            logger.error(f"Failed to send approval request for: {user.email}")

    return {
        "message": "Subscription request received — pending admin approval.",
        "user": {
            "email": user.email,
            "name": user.name,
            "status": "pending",
        }
    }


# ── Approve ───────────────────────────────────────────────────────────────────

@router.get("/approve", response_class=HTMLResponse)
async def approve_user(token: str):
    """
    One-click approve endpoint — linked from admin approval email.
    Sets active=1 and sends a welcome email to the subscriber.
    """
    async with get_db() as db:
        user = await db.approve_user(token)

    if not user:
        return _html_response(
            title="Link Expired",
            message="This approval link is invalid or has already been used.",
            colour="#ef4444",
            icon="⚠️",
        )

    # Send welcome email to the new subscriber
    app_url = os.getenv("APP_URL", "https://ai-signal.app")
    await send_email(
        to_email=user.email,
        subject="🎉 You're in — Welcome to AI Signal!",
        html_body=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:40px auto;
                    padding:36px;background:#fff;border-radius:12px;
                    box-shadow:0 2px 12px rgba(0,0,0,0.08)">
          <div style="font-size:11px;font-weight:700;letter-spacing:2px;
                      text-transform:uppercase;color:#888;margin-bottom:16px">
            AI Signal
          </div>
          <h2 style="font-size:22px;font-weight:700;color:#111;margin:0 0 12px">
            Welcome aboard, {user.name}! 🎉
          </h2>
          <p style="color:#555;font-size:15px;line-height:1.6">
            Your subscription has been approved. You'll receive your first
            AI/ML digest tomorrow morning at <strong>8:00 AM UTC</strong>.
          </p>
          <p style="color:#555;font-size:15px;line-height:1.6">
            In the meantime, browse today's stories:
          </p>
          <a href="{app_url}" style="display:inline-block;margin-top:8px;
             padding:12px 24px;background:#111;color:#fff;border-radius:8px;
             text-decoration:none;font-weight:600;font-size:15px">
            Browse AI Signal →
          </a>
          <p style="margin-top:28px;font-size:12px;color:#bbb">
            AI Signal · {app_url}
          </p>
        </div>
        """,
    )
    logger.info(f"✅ Approved and welcomed: {user.email}")

    return _html_response(
        title="Approved!",
        message=f"{user.name} ({user.email}) has been approved and will receive digests from tomorrow.",
        colour="#16a34a",
        icon="✅",
    )


# ── Reject ────────────────────────────────────────────────────────────────────

@router.get("/reject", response_class=HTMLResponse)
async def reject_user(token: str):
    """
    One-click reject endpoint — linked from admin approval email.
    Deletes the pending subscriber and sends them a polite rejection email.
    """
    async with get_db() as db:
        user = await db.reject_user(token)

    if not user:
        return _html_response(
            title="Link Expired",
            message="This rejection link is invalid or has already been used.",
            colour="#ef4444",
            icon="⚠️",
        )

    # Notify the subscriber politely
    await send_rejection_email(
        subscriber_email=user.email,
        subscriber_name=user.name,
    )
    logger.info(f"Rejected and notified: {user.email}")

    return _html_response(
        title="Rejected",
        message=f"{user.name} ({user.email}) has been rejected and notified by email.",
        colour="#6b7280",
        icon="❌",
    )


# ── Unsubscribe ──────────────────────────────────────────────────────────────

@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str):
    """
    One-click unsubscribe endpoint — linked from every digest email footer.
    Uses a personal token so no login required.
    """
    async with get_db() as db:
        user = await db.unsubscribe_by_token(token)

    if not user:
        return _html_response(
            title="Link Expired",
            message="This unsubscribe link is invalid or has already been used.",
            colour="#ef4444",
            icon="⚠️",
        )

    logger.info(f"Unsubscribed: {user.email}")
    return _html_response(
        title="Unsubscribed",
        message=f"{user.name}, you've been removed from AI Signal. You won't receive any more digest emails.",
        colour="#6b7280",
        icon="✅",
    )


# ── List pending (admin) ──────────────────────────────────────────────────────

@router.get("/pending")
async def list_pending():
    """Admin endpoint — list all subscribers awaiting approval."""
    async with get_db() as db:
        users = await db.get_pending_users()
    return {
        "pending": [
            {"email": u.email, "name": u.name, "min_relevance": u.min_relevance}
            for u in users
        ],
        "count": len(users),
    }


# ── Existing endpoints ────────────────────────────────────────────────────────

@router.get("")
async def list_users():
    async with get_db() as db:
        users = await db.get_active_users()
    return {"users": [u.to_dict() for u in users]}


@router.delete("/{email}")
async def delete_user(email: str):
    async with get_db() as db:
        await db.delete_user(email)
    return {"message": f"User {email} removed"}


# ── HTML response helper ──────────────────────────────────────────────────────

def _html_response(title: str, message: str, colour: str, icon: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — AI Signal</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f5; margin: 0; padding: 60px 20px; text-align: center; }}
  .card {{ background: #fff; border-radius: 12px; max-width: 420px; margin: 0 auto;
           padding: 48px 36px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
  .icon {{ font-size: 48px; margin-bottom: 16px; }}
  h1 {{ font-size: 24px; font-weight: 700; color: {colour}; margin: 0 0 12px; }}
  p {{ color: #555; font-size: 15px; line-height: 1.6; margin: 0; }}
  a {{ display: inline-block; margin-top: 28px; color: #888; font-size: 13px; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <a href="https://ai-signal.app">← Back to AI Signal</a>
</div>
</body>
</html>"""
