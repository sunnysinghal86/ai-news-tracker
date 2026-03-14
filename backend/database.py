"""
database.py — updated with approval workflow

Changes:
  - users table: added approval_token TEXT, active defaults to 0 (pending)
  - create_user(): sets active=0, generates approval token
  - approve_user(token): sets active=1
  - reject_user(token): deletes user
  - get_pending_users(): lists users awaiting approval
  - Migration: ALTER TABLE adds approval_token if upgrading existing DB
"""

import os
import json
import hashlib
import secrets
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/tmp/news_tracker.db")
_db = None


class User:
    def __init__(self, id, email, name, active, categories, min_relevance,
                 approval_token=None):
        self.id = id
        self.email = email
        self.name = name
        self.active = active
        self.categories = categories
        self.min_relevance = min_relevance
        self.approval_token = approval_token

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "active": self.active,
            "categories": self.categories,
            "min_relevance": self.min_relevance,
        }


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

    async def disconnect(self):
        if self._db:
            await self._db.close()

    async def init_schema(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                source TEXT,
                author TEXT,
                score INTEGER DEFAULT 0,
                published_at TEXT,
                fetched_at TEXT DEFAULT (datetime('now')),
                summary TEXT,
                category TEXT,
                tags TEXT,
                relevance_score INTEGER DEFAULT 5,
                is_product_or_tool INTEGER DEFAULT 0,
                product_name TEXT,
                competitors TEXT,
                competitive_advantage TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score);
            CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
            CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at);

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                active INTEGER DEFAULT 0,
                categories TEXT,
                min_relevance INTEGER DEFAULT 5,
                created_at TEXT NOT NULL,
                approval_token TEXT
            );

            CREATE TABLE IF NOT EXISTS digest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                article_count INTEGER,
                status TEXT
            );
        """)

        # Migration: add approval_token column to existing DBs
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN approval_token TEXT")
            await self._db.commit()
            logger.info("Migrated users table: added approval_token column")
        except Exception:
            pass  # Column already exists — fine

        # Migration: ensure active defaults to 0 for new subscribers
        # (existing seeded users stay active=1 — handled in create_user)
        await self._db.commit()

    # ── Articles ──────────────────────────────────────────────────────────────

    async def get_summarised_ids(self) -> set:
        async with self._db.execute(
            """SELECT id FROM articles
               WHERE LENGTH(summary) > 20
               AND NOT (is_product_or_tool=1
                        AND (competitors IS NULL OR competitors='[]'))"""
        ) as cur:
            rows = await cur.fetchall()
        return {r["id"] for r in rows}

    async def upsert_articles(self, articles: list):
        for a in articles:
            await self._db.execute(
                """INSERT INTO articles
                   (id,title,url,source,author,score,published_at,
                    summary,category,tags,relevance_score,
                    is_product_or_tool,product_name,competitors,competitive_advantage)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                    summary=excluded.summary,
                    category=excluded.category,
                    tags=excluded.tags,
                    relevance_score=excluded.relevance_score,
                    is_product_or_tool=excluded.is_product_or_tool,
                    product_name=excluded.product_name,
                    competitors=excluded.competitors,
                    competitive_advantage=excluded.competitive_advantage""",
                (
                    a.id, a.title, a.url, a.source, a.author, a.score,
                    a.published_at, a.summary, a.category,
                    json.dumps(a.tags or []),
                    a.relevance_score, int(a.is_product_or_tool),
                    a.product_name,
                    json.dumps(a.competitors or []),
                    a.competitive_advantage,
                )
            )
        await self._db.commit()

    async def get_articles(self, limit=50, offset=0, category=None,
                           source=None, min_relevance=0, search=None):
        conditions = ["1=1"]
        params = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if source:
            conditions.append("source LIKE ?")
            params.append(f"%{source}%")
        if min_relevance:
            conditions.append("relevance_score >= ?")
            params.append(min_relevance)
        if search:
            conditions.append("(title LIKE ? OR summary LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions)
        async with self._db.execute(
            f"SELECT * FROM articles WHERE {where} "
            f"ORDER BY relevance_score DESC, fetched_at DESC "
            f"LIMIT ? OFFSET ?",
            params + [limit, offset]
        ) as cur:
            rows = await cur.fetchall()
        return [self._to_dict(r) for r in rows]

    async def get_top_articles(self, limit=10, min_relevance=5,
                               categories=None, hours=24):
        for window in [hours, 48, 168]:
            params = [min_relevance, window]
            cat_clause = ""
            if categories:
                placeholders = ",".join("?" * len(categories))
                cat_clause = f"AND category IN ({placeholders})"
                params = [min_relevance, window] + list(categories)
            query = f"""
                SELECT * FROM articles
                WHERE relevance_score >= ?
                AND summary IS NOT NULL AND LENGTH(summary) > 40
                AND fetched_at >= datetime('now', '-' || ? || ' hours')
                {cat_clause}
                ORDER BY relevance_score DESC, fetched_at DESC
                LIMIT {limit}
            """
            async with self._db.execute(query, params) as cur:
                rows = await cur.fetchall()
            articles = [self._to_dict(r) for r in rows]
            if len(articles) >= 5:
                return articles
        async with self._db.execute(
            "SELECT * FROM articles WHERE relevance_score >= ? "
            "AND summary IS NOT NULL AND LENGTH(summary) > 40 "
            "ORDER BY relevance_score DESC, fetched_at DESC LIMIT ?",
            (min_relevance, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._to_dict(r) for r in rows]

    async def get_stats(self):
        async with self._db.execute("SELECT COUNT(*) as n FROM articles") as c:
            total = (await c.fetchone())["n"]
        async with self._db.execute(
            "SELECT COUNT(*) as n FROM articles WHERE is_product_or_tool=1"
        ) as c:
            products = (await c.fetchone())["n"]
        async with self._db.execute(
            "SELECT category, COUNT(*) as n FROM articles GROUP BY category ORDER BY n DESC"
        ) as c:
            cats = await c.fetchall()
        return {
            "total_articles": total,
            "product_articles": products,
            "by_category": {r["category"]: r["n"] for r in cats},
        }

    # ── Users ─────────────────────────────────────────────────────────────────

    async def create_user(self, email: str, name: str,
                          categories=None, min_relevance: int = 5,
                          require_approval: bool = True) -> "User":
        """
        Create a new subscriber.

        require_approval=True  → active=0, generates approval_token (default for web signups)
        require_approval=False → active=1, no token (used for SEED_SUBSCRIBERS)
        """
        now = datetime.now(timezone.utc).isoformat()
        token = secrets.token_urlsafe(32) if require_approval else None
        active = 0 if require_approval else 1

        await self._db.execute(
            "INSERT OR IGNORE INTO users "
            "(email, name, active, categories, min_relevance, created_at, approval_token) "
            "VALUES (?,?,?,?,?,?,?)",
            (email, name, active,
             json.dumps(categories or []), min_relevance, now, token),
        )
        await self._db.commit()
        return await self.get_user_by_email(email)

    async def approve_user(self, token: str) -> Optional["User"]:
        """Approve a pending subscriber by token. Returns user if found."""
        async with self._db.execute(
            "SELECT * FROM users WHERE approval_token=?", (token,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        await self._db.execute(
            "UPDATE users SET active=1, approval_token=NULL WHERE approval_token=?",
            (token,)
        )
        await self._db.commit()
        return await self.get_user_by_email(row["email"])

    async def reject_user(self, token: str) -> bool:
        """Reject and delete a pending subscriber by token."""
        async with self._db.execute(
            "SELECT email FROM users WHERE approval_token=?", (token,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return False
        await self._db.execute(
            "DELETE FROM users WHERE approval_token=?", (token,)
        )
        await self._db.commit()
        logger.info(f"Rejected and removed subscriber: {row['email']}")
        return True

    async def get_user_by_email(self, email: str) -> Optional["User"]:
        async with self._db.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        return User(
            id=row["id"], email=row["email"], name=row["name"],
            active=bool(row["active"]),
            categories=json.loads(row["categories"] or "[]"),
            min_relevance=row["min_relevance"],
            approval_token=row["approval_token"],
        )

    async def get_active_users(self) -> List["User"]:
        async with self._db.execute("SELECT * FROM users WHERE active=1") as c:
            rows = await c.fetchall()
        return [
            User(id=r["id"], email=r["email"], name=r["name"],
                 active=True,
                 categories=json.loads(r["categories"] or "[]"),
                 min_relevance=r["min_relevance"])
            for r in rows
        ]

    async def get_pending_users(self) -> List["User"]:
        """Return subscribers awaiting approval."""
        async with self._db.execute(
            "SELECT * FROM users WHERE active=0 AND approval_token IS NOT NULL"
        ) as c:
            rows = await c.fetchall()
        return [
            User(id=r["id"], email=r["email"], name=r["name"],
                 active=False,
                 categories=json.loads(r["categories"] or "[]"),
                 min_relevance=r["min_relevance"],
                 approval_token=r["approval_token"])
            for r in rows
        ]

    async def delete_user(self, email: str):
        await self._db.execute("DELETE FROM users WHERE email=?", (email,))
        await self._db.commit()

    async def log_digest(self, email: str, article_count: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO digest_log (sent_at, recipient_email, article_count, status) "
            "VALUES (?,?,?,?)",
            (now, email, article_count, status)
        )
        await self._db.commit()

    def _to_dict(self, row) -> dict:
        d = dict(row)
        for f in ("tags", "competitors"):
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    d[f] = []
        return d


# ── Global DB singleton ───────────────────────────────────────────────────────

async def init_db():
    global _db
    _db = Database(DB_PATH)
    await _db.connect()
    await _db.init_schema()
    logger.info(f"Database ready at {DB_PATH}")


@asynccontextmanager
async def get_db():
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    yield _db
