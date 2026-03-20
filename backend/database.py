"""
database.py — Turso/libSQL cloud database

Replaces aiosqlite (local /tmp SQLite) with libsql (Turso cloud SQLite).
Data survives Render restarts — articles and subscribers persist permanently.

Setup:
  1. pip install libsql
  2. Create Turso DB: turso db create ai-signal
  3. Get URL + token: turso db show ai-signal && turso db tokens create ai-signal
  4. Set env vars: TURSO_URL and TURSO_TOKEN

The libsql API mirrors aiosqlite closely:
  aiosqlite: async with self._db.execute(sql) as cur: rows = await cur.fetchall()
  libsql:    rs = await self._conn.execute(sql);   rows = rs.rows

All SQL is identical — only the connection and row access patterns change.
"""

import os
import json
import secrets
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Connection config ─────────────────────────────────────────────────────────
TURSO_URL   = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

# Fallback to local SQLite if Turso not configured (useful for local dev)
# libsql accepts file: URLs for local SQLite files
LOCAL_DB    = os.getenv("DB_PATH", "/tmp/news_tracker.db")

_db = None  # global Database instance


# ── Row helper ────────────────────────────────────────────────────────────────

class Row(dict):
    """Dict subclass that supports both row["col"] and row.col access."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _make_rows(rs) -> List[Row]:
    """Convert libsql ResultSet to list of Row dicts."""
    cols = list(rs.columns)
    return [Row(zip(cols, row)) for row in rs.rows]


# ── User model ────────────────────────────────────────────────────────────────

class User:
    def __init__(self, id, email, name, active, categories,
                 min_relevance, approval_token=None):
        self.id             = id
        self.email          = email
        self.name           = name
        self.active         = active
        self.categories     = categories
        self.min_relevance  = min_relevance
        self.approval_token = approval_token

    def to_dict(self):
        return {
            "id":            self.id,
            "email":         self.email,
            "name":          self.name,
            "active":        self.active,
            "categories":    self.categories,
            "min_relevance": self.min_relevance,
        }


# ── Category normaliser ───────────────────────────────────────────────────────

_VALID_CATS = {
    "Product/Tool", "AI Model", "Research Paper",
    "Industry News", "Tutorial/Guide", "Platform/Infrastructure"
}

def _normalise_category(raw: str) -> str:
    if not raw:
        return "Industry News"
    if raw in _VALID_CATS:
        return raw
    r = raw.lower()
    if any(x in r for x in ["product", "tool", "sdk", "library", "framework", "saas", "cli"]):
        return "Product/Tool"
    if any(x in r for x in ["ai model", "llm", "embedding", "image model"]):
        return "AI Model"
    if any(x in r for x in ["research", "paper", "preprint", "academic"]):
        return "Research Paper"
    if any(x in r for x in ["tutorial", "guide", "how-to", "practice"]):
        return "Tutorial/Guide"
    if any(x in r for x in ["platform", "infra", "mlops", "deployment", "devops", "cloud"]):
        return "Platform/Infrastructure"
    return "Industry News"


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    def __init__(self):
        self._conn = None

    async def connect(self):
        import libsql
        if TURSO_URL and TURSO_TOKEN:
            logger.info(f"Connecting to Turso: {TURSO_URL}")
            self._conn = libsql.connect(
                database=TURSO_URL,
                auth_token=TURSO_TOKEN,
                sync_url=TURSO_URL,
            )
            await self._conn.sync()
            logger.info("Connected to Turso cloud database")
        else:
            logger.warning("TURSO_URL/TOKEN not set — falling back to local SQLite")
            self._conn = libsql.connect(LOCAL_DB)
        return self

    async def disconnect(self):
        if self._conn:
            self._conn.close()

    async def _exec(self, sql: str, params=None):
        """Execute a write statement."""
        if params:
            await self._conn.execute(sql, params)
        else:
            await self._conn.execute(sql)
        await self._conn.commit()

    async def _query(self, sql: str, params=None) -> List[Row]:
        """Execute a read statement, return list of Row dicts."""
        if params:
            rs = await self._conn.execute(sql, params)
        else:
            rs = await self._conn.execute(sql)
        return _make_rows(rs)

    async def init_schema(self):
        """Create tables if they don't exist. Safe to run on every startup."""
        statements = [
            """CREATE TABLE IF NOT EXISTS articles (
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
            )""",
            "CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score)",
            "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)",
            "CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at)",
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                active INTEGER DEFAULT 0,
                categories TEXT,
                min_relevance INTEGER DEFAULT 5,
                created_at TEXT NOT NULL,
                approval_token TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS digest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                article_count INTEGER,
                status TEXT
            )""",
        ]
        for stmt in statements:
            await self._conn.execute(stmt)
        await self._conn.commit()

        # Migration: add approval_token column if upgrading from old schema
        try:
            await self._conn.execute("ALTER TABLE users ADD COLUMN approval_token TEXT")
            await self._conn.commit()
            logger.info("Migration: added approval_token column")
        except Exception:
            pass  # Column already exists

        # Sync to Turso cloud after schema setup
        if TURSO_URL and TURSO_TOKEN:
            await self._conn.sync()
        logger.info("Schema ready")

    # ── Articles ──────────────────────────────────────────────────────────────

    async def get_summarised_ids(self) -> set:
        rows = await self._query(
            """SELECT id FROM articles
               WHERE LENGTH(summary) > 20
               AND NOT (is_product_or_tool=1
                        AND (competitors IS NULL OR competitors='[]'))"""
        )
        return {r["id"] for r in rows}

    async def upsert_articles(self, articles: list):
        for a in articles:
            await self._conn.execute(
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
                    a.published_at, a.summary,
                    _normalise_category(a.category),
                    json.dumps(a.tags or []),
                    a.relevance_score, int(a.is_product_or_tool),
                    a.product_name,
                    json.dumps(a.competitors or []),
                    a.competitive_advantage,
                )
            )
        await self._conn.commit()
        if TURSO_URL and TURSO_TOKEN:
            await self._conn.sync()

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
        rows = await self._query(
            f"SELECT * FROM articles WHERE {where} "
            f"ORDER BY relevance_score DESC, fetched_at DESC "
            f"LIMIT ? OFFSET ?",
            params + [limit, offset]
        )
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
            rows = await self._query(query, params)
            articles = [self._to_dict(r) for r in rows]
            if len(articles) >= 5:
                logger.info(f"Digest: {len(articles)} articles from last {window}h")
                return articles
        rows = await self._query(
            "SELECT * FROM articles WHERE relevance_score >= ? "
            "AND summary IS NOT NULL AND LENGTH(summary) > 40 "
            "ORDER BY relevance_score DESC, fetched_at DESC LIMIT ?",
            (min_relevance, limit),
        )
        return [self._to_dict(r) for r in rows]

    async def get_stats(self):
        rows = await self._query("SELECT COUNT(*) as n FROM articles")
        total = rows[0]["n"] if rows else 0
        rows = await self._query(
            "SELECT COUNT(*) as n FROM articles WHERE is_product_or_tool=1"
        )
        products = rows[0]["n"] if rows else 0
        cats = await self._query(
            "SELECT category, COUNT(*) as n FROM articles "
            "GROUP BY category ORDER BY n DESC"
        )
        return {
            "total_articles":   total,
            "product_articles": products,
            "by_category":      {r["category"]: r["n"] for r in cats},
        }

    # ── Users ─────────────────────────────────────────────────────────────────

    async def create_user(self, email: str, name: str,
                          categories=None, min_relevance: int = 5,
                          require_approval: bool = True) -> "User":
        now   = datetime.now(timezone.utc).isoformat()
        token = secrets.token_urlsafe(32) if require_approval else None
        active = 0 if require_approval else 1
        try:
            await self._conn.execute(
                "INSERT OR IGNORE INTO users "
                "(email, name, active, categories, min_relevance, created_at, approval_token) "
                "VALUES (?,?,?,?,?,?,?)",
                (email, name, active,
                 json.dumps(categories or []), min_relevance, now, token),
            )
            await self._conn.commit()
            if TURSO_URL and TURSO_TOKEN:
                await self._conn.sync()
        except Exception as e:
            logger.error(f"create_user error: {e}")
        return await self.get_user_by_email(email)

    async def approve_user(self, token: str) -> Optional["User"]:
        rows = await self._query(
            "SELECT * FROM users WHERE approval_token=?", (token,)
        )
        if not rows:
            return None
        await self._exec(
            "UPDATE users SET active=1, approval_token=NULL WHERE approval_token=?",
            (token,)
        )
        return await self.get_user_by_email(rows[0]["email"])

    async def reject_user(self, token: str) -> bool:
        rows = await self._query(
            "SELECT email FROM users WHERE approval_token=?", (token,)
        )
        if not rows:
            return False
        await self._exec(
            "DELETE FROM users WHERE approval_token=?", (token,)
        )
        return True

    async def get_user_by_email(self, email: str) -> Optional["User"]:
        rows = await self._query(
            "SELECT * FROM users WHERE email=?", (email,)
        )
        if not rows:
            return None
        r = rows[0]
        return User(
            id=r["id"], email=r["email"], name=r["name"],
            active=bool(r["active"]),
            categories=json.loads(r["categories"] or "[]"),
            min_relevance=r["min_relevance"],
            approval_token=r.get("approval_token"),
        )

    async def get_active_users(self) -> List["User"]:
        rows = await self._query("SELECT * FROM users WHERE active=1")
        return [
            User(id=r["id"], email=r["email"], name=r["name"],
                 active=True,
                 categories=json.loads(r["categories"] or "[]"),
                 min_relevance=r["min_relevance"])
            for r in rows
        ]

    async def get_pending_users(self) -> List["User"]:
        rows = await self._query(
            "SELECT * FROM users WHERE active=0 AND approval_token IS NOT NULL"
        )
        return [
            User(id=r["id"], email=r["email"], name=r["name"],
                 active=False,
                 categories=json.loads(r["categories"] or "[]"),
                 min_relevance=r["min_relevance"],
                 approval_token=r["approval_token"])
            for r in rows
        ]

    async def delete_user(self, email: str):
        await self._exec("DELETE FROM users WHERE email=?", (email,))

    async def log_digest(self, email: str, article_count: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO digest_log (sent_at, recipient_email, article_count, status) "
            "VALUES (?,?,?,?)",
            (now, email, article_count, status)
        )

    def _to_dict(self, row: Row) -> dict:
        d = dict(row)
        d["category"] = _normalise_category(d.get("category", ""))
        for f in ("tags", "competitors"):
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    d[f] = []
        return d


# ── Global singleton ──────────────────────────────────────────────────────────

async def init_db():
    global _db
    _db = Database()
    await _db.connect()
    await _db.init_schema()
    logger.info("Database ready")


@asynccontextmanager
async def get_db():
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    yield _db
