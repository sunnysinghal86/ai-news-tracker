"""
database.py — Turso via libsql embedded replica

libsql uses SYNCHRONOUS calls with a local SQLite replica that syncs to Turso cloud.
We run all DB operations in a thread pool executor so they don't block FastAPI's event loop.

Pattern:
  conn = libsql.connect("local.db", sync_url=TURSO_URL, auth_token=TURSO_TOKEN)
  conn.sync()                      # pull latest from Turso on startup
  conn.execute(sql, params)        # read/write local replica
  conn.commit()                    # commit locally
  conn.sync()                      # push to Turso after writes

Falls back to plain local SQLite if TURSO_URL not set (local dev).
"""

import os
import json
import secrets
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import partial
from typing import List, Optional

import libsql

logger = logging.getLogger(__name__)

TURSO_URL   = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")
LOCAL_DB    = os.getenv("DB_PATH", "/tmp/news_tracker.db")

_db = None   # global Database instance


# ── Row helper ────────────────────────────────────────────────────────────────

class Row(dict):
    """Dict-like row that supports row["col"] and row.col access."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _rows_from_cursor(cur) -> List[Row]:
    """Convert a libsql cursor to list of Row dicts."""
    cols = [d[0] for d in cur.description] if cur.description else []
    return [Row(zip(cols, row)) for row in (cur.fetchall() or [])]


# ── Category normaliser ───────────────────────────────────────────────────────

_VALID_CATS = {
    "Product/Tool", "AI Model", "Research Paper",
    "Industry News", "Tutorial/Guide", "Platform/Infrastructure"
}

# Sources that always produce research content — override Claude's category
_COMPANY_BLOG_SOURCES = {"Anthropic Blog", "OpenAI Blog", "Google AI Blog", "AWS AI Blog"}

def _normalise_category(raw: str, source: str = "") -> str:
    # Source-based overrides take priority over Claude's output
    if source in _COMPANY_BLOG_SOURCES:
        # Company blogs publish both models and products — trust Claude but fix bad defaults
        if raw in _VALID_CATS and raw != "Industry News":
            return raw
        return "AI Model"  # safer default for company blogs than Industry News
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


# ── User model ────────────────────────────────────────────────────────────────

class User:
    def __init__(self, id, email, name, active, categories,
                 min_relevance, approval_token=None, unsubscribe_token=None):
        self.id                = id
        self.email             = email
        self.name              = name
        self.active            = active
        self.categories        = categories
        self.min_relevance     = min_relevance
        self.approval_token    = approval_token
        self.unsubscribe_token = unsubscribe_token

    def to_dict(self):
        return {
            "id":            self.id,
            "email":         self.email,
            "name":          self.name,
            "active":        self.active,
            "categories":    self.categories,
            "min_relevance": self.min_relevance,
        }


# ── Database class ────────────────────────────────────────────────────────────

class Database:
    def __init__(self):
        self._conn = None
        self._loop = None
        self._executor = None

    async def connect(self):
        self._loop = asyncio.get_event_loop()
        # Connect in thread pool — libsql.connect() is blocking
        await self._run(self._connect_sync)
        logger.info("Database connected")

    def _connect_sync(self):
        """Runs in thread pool — establishes libsql connection."""
        if TURSO_URL and TURSO_TOKEN:
            logger.info(f"Connecting to Turso: {TURSO_URL}")
            self._conn = libsql.connect(
                "ai_signal.db",          # local replica filename
                sync_url=TURSO_URL,
                auth_token=TURSO_TOKEN,
            )
            self._conn.sync()            # pull latest from Turso on startup
            logger.info("Connected to Turso (embedded replica)")
        else:
            logger.warning("TURSO_URL not set — using local SQLite fallback")
            self._conn = libsql.connect(LOCAL_DB)

    async def disconnect(self):
        if self._conn:
            await self._run(self._conn.close)

    async def _run(self, func, *args, **kwargs):
        """Run a blocking function in the thread pool executor."""
        if args or kwargs:
            func = partial(func, *args, **kwargs)
        return await self._loop.run_in_executor(None, func)

    def _exec_sync(self, sql: str, params=None):
        """Synchronous execute + commit + sync to Turso."""
        if params:
            self._conn.execute(sql, params)
        else:
            self._conn.execute(sql)
        self._conn.commit()
        if TURSO_URL and TURSO_TOKEN:
            self._conn.sync()

    def _query_sync(self, sql: str, params=None) -> List[Row]:
        """Synchronous query, returns list of Row dicts."""
        if params:
            cur = self._conn.execute(sql, params)
        else:
            cur = self._conn.execute(sql)
        return _rows_from_cursor(cur)

    async def _exec(self, sql: str, params=None):
        await self._run(self._exec_sync, sql, params)

    async def _query(self, sql: str, params=None) -> List[Row]:
        return await self._run(self._query_sync, sql, params)

    # ── Schema ────────────────────────────────────────────────────────────────

    async def init_schema(self):
        def _setup():
            stmts = [
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
                    approval_token TEXT,
                    unsubscribe_token TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS digest_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sent_at TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    article_count INTEGER,
                    status TEXT
                )""",
            ]
            for stmt in stmts:
                self._conn.execute(stmt)
            self._conn.commit()
            # Migration: add approval_token column if upgrading
            try:
                self._conn.execute("ALTER TABLE users ADD COLUMN approval_token TEXT")
                self._conn.commit()
                logger.info("Migration: added approval_token column")
            except Exception:
                pass  # already exists
            try:
                self._conn.execute("ALTER TABLE users ADD COLUMN unsubscribe_token TEXT")
                self._conn.commit()
                logger.info("Migration: added unsubscribe_token column")
            except Exception:
                pass  # already exists
            if TURSO_URL and TURSO_TOKEN:
                self._conn.sync()
            logger.info("Schema ready")

        await self._run(_setup)

    # ── Articles ──────────────────────────────────────────────────────────────

    async def get_summarised_ids(self) -> set:
        """Returns IDs already processed — articles with a summary and
        product/AI Model articles that have competitor data.
        Only re-queues recent articles (last 14 days) to avoid mass reprocessing."""
        rows = await self._query(
            """SELECT id FROM articles
               WHERE LENGTH(summary) > 20
               AND NOT (
                   is_product_or_tool=1
                   AND (competitors IS NULL OR competitors='[]')
                   AND fetched_at >= datetime('now', '-14 days')
               )"""
        )
        return {r["id"] for r in rows}

    async def upsert_articles(self, articles: list):
        def _upsert():
            for a in articles:
                self._conn.execute(
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
                        competitive_advantage=excluded.competitive_advantage,
                        fetched_at=datetime('now')""",
                    (
                        a.id, a.title, a.url, a.source, a.author, a.score,
                        a.published_at, a.summary,
                        _normalise_category(a.category, a.source),
                        json.dumps(a.tags or []),
                        a.relevance_score, int(a.is_product_or_tool),
                        a.product_name,
                        json.dumps(a.competitors or []),
                        a.competitive_advantage,
                    )
                )
            self._conn.commit()
            if TURSO_URL and TURSO_TOKEN:
                self._conn.sync()
        await self._run(_upsert)

    async def get_articles(self, limit=50, offset=0, category=None,
                           source=None, min_relevance=0, search=None,
                           days=7):
        """
        Return articles from the last `days` days (default 7).
        Older articles are kept in DB for digest fallback but hidden from the UI feed.
        Set days=0 to return all articles regardless of age.
        """
        conditions = ["1=1"]
        params = []
        if days:
            # Filter by published_at — the actual article date.
            # Simpler and more correct than MAX(published_at, fetched_at).
            # Articles with null/bad published_at are excluded (correct behaviour).
            conditions.append(
                "substr(published_at, 1, 10) >= date('now', ? || ' days')"
            )
            params.append(f"-{days}")
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
        # Use ROW_NUMBER to limit max 5 articles per source in UI results.
        # This prevents any single source (Medium: 61 articles) from dominating
        # the feed even when they have high relevance scores.
        # The outer query then applies the user's requested limit/offset.
        inner_where = where
        rows = await self._query(
            f"""SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY source
                        ORDER BY relevance_score DESC, published_at DESC
                    ) as rn
                FROM articles
                WHERE {inner_where}
            ) ranked
            WHERE rn <= 5
            ORDER BY relevance_score DESC, published_at DESC
            LIMIT ? OFFSET ?""",
            params + [limit, offset]
        )
        return [self._to_dict(r) for r in rows]

    # Active sources for digest — retired sources excluded even if still in DB
    ACTIVE_SOURCES = [
        "Medium", "platformengineering.org", "Anthropic Blog",
        "OpenAI Blog", "Google AI Blog", "AWS AI Blog", "NewsAPI",
        "Stack Overflow Blog", "InfoQ", "The New Stack",
    ]

    async def get_top_articles(self, limit=30, min_relevance=5,
                               categories=None, hours=24):
        """
        Fetch top articles for digest.
        min_relevance is used as a PREFERENCE not a hard cutoff —
        articles below threshold are included as fallback to guarantee
        the digest always has enough content.
        Always restricted to active sources only.
        """
        src_placeholders = ",".join("?" * len(self.ACTIVE_SOURCES))
        src_clause = f"AND source IN ({src_placeholders})"

        cat_clause = ""
        cat_params = []
        if categories:
            placeholders = ",".join("?" * len(categories))
            cat_clause = f"AND category IN ({placeholders})"
            cat_params = list(categories)

        # Try preferred window with min_relevance
        for window in [hours, 48, 168]:
            params = [min_relevance, window] + list(self.ACTIVE_SOURCES) + cat_params
            rows = await self._query(f"""
                SELECT * FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY source
                            ORDER BY relevance_score DESC, fetched_at DESC
                        ) as rn
                    FROM articles
                    WHERE relevance_score >= ?
                    AND summary IS NOT NULL AND LENGTH(summary) > 40
                    AND fetched_at >= datetime('now', '-' || ? || ' hours')
                    {src_clause} {cat_clause}
                ) ranked
                WHERE rn <= 5
                ORDER BY relevance_score DESC, fetched_at DESC
                LIMIT {limit}
            """, params)
            articles = [self._to_dict(r) for r in rows]
            if len(articles) >= 10:
                logger.info(f"Digest: {len(articles)} articles (last {window}h, min={min_relevance})")
                return articles

        # Fallback — drop min_relevance entirely, return best available by score
        logger.info(f"Digest: falling back to score>=5, no time limit")
        params = [5] + list(self.ACTIVE_SOURCES) + cat_params + [limit]
        rows = await self._query(f"""
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY source
                        ORDER BY relevance_score DESC, fetched_at DESC
                    ) as rn
                FROM articles
                WHERE relevance_score >= 5
                AND summary IS NOT NULL AND LENGTH(summary) > 40
                {src_clause} {cat_clause}
            ) ranked
            WHERE rn <= 5
            ORDER BY relevance_score DESC, fetched_at DESC
            LIMIT ?
        """, params)
        articles = [self._to_dict(r) for r in rows]
        logger.info(f"Digest fallback: {len(articles)} articles")
        return articles


        # Phase 2 — relax min_relevance by 1 point, try 7 days
        relaxed = max(5, min_relevance - 1)
        if relaxed < min_relevance:
            query, params = build_query(168, relaxed)
            rows     = await self._query(query, params)
            articles = [self._to_dict(r) for r in rows]
            if len(articles) >= 10:
                logger.info(f"Digest: {len(articles)} articles (relaxed to min={relaxed})")
                return articles

        # Phase 3 — final fallback: no time limit, floor at 5
        floor = max(5, min_relevance - 2)
        params = [floor] + list(self.ACTIVE_SOURCES) + [limit]
        rows = await self._query(
            f"SELECT * FROM articles WHERE relevance_score >= ? "
            f"AND summary IS NOT NULL AND LENGTH(summary) > 40 "
            f"AND source IN ({src_placeholders}) "
            f"ORDER BY relevance_score DESC LIMIT ?",
            params,
        )
        articles = [self._to_dict(r) for r in rows]
        logger.info(f"Digest fallback: {len(articles)} articles (floor={floor}, no time limit)")
        return articles

    async def get_stats(self):
        rows  = await self._query("SELECT COUNT(*) as n FROM articles")
        total = rows[0]["n"] if rows else 0
        rows  = await self._query(
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
        now    = datetime.now(timezone.utc).isoformat()
        token           = secrets.token_urlsafe(32) if require_approval else None
        unsub_token     = secrets.token_urlsafe(32)  # always generated
        active          = 0 if require_approval else 1
        try:
            await self._exec(
                "INSERT OR IGNORE INTO users "
                "(email,name,active,categories,min_relevance,created_at,approval_token,unsubscribe_token) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (email, name, active,
                 json.dumps(categories or []), min_relevance, now, token, unsub_token),
            )
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

    async def reject_user(self, token: str) -> Optional["User"]:
        """Reject and delete a pending subscriber. Returns the user before deletion."""
        rows = await self._query(
            "SELECT * FROM users WHERE approval_token=?", (token,)
        )
        if not rows:
            return None
        r = rows[0]
        rejected_user = User(
            id=r["id"], email=r["email"], name=r["name"],
            active=False,
            categories=json.loads(r.get("categories") or "[]"),
            min_relevance=r["min_relevance"],
        )
        await self._exec(
            "DELETE FROM users WHERE approval_token=?", (token,)
        )
        return rejected_user

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
            categories=json.loads(r.get("categories") or "[]"),
            min_relevance=r["min_relevance"],
            approval_token=r.get("approval_token"),
            unsubscribe_token=r.get("unsubscribe_token"),
        )

    async def get_active_users(self) -> List["User"]:
        rows = await self._query("SELECT * FROM users WHERE active=1")
        return [
            User(id=r["id"], email=r["email"], name=r["name"],
                 active=True,
                 categories=json.loads(r.get("categories") or "[]"),
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
                 categories=json.loads(r.get("categories") or "[]"),
                 min_relevance=r["min_relevance"],
                 approval_token=r.get("approval_token"))
            for r in rows
        ]

    async def delete_user(self, email: str):
        await self._exec("DELETE FROM users WHERE email=?", (email,))

    async def unsubscribe_by_token(self, token: str) -> Optional["User"]:
        """Unsubscribe a user via their personal unsubscribe token."""
        rows = await self._query(
            "SELECT * FROM users WHERE unsubscribe_token=?", (token,)
        )
        if not rows:
            return None
        r = rows[0]
        user = User(
            id=r["id"], email=r["email"], name=r["name"],
            active=bool(r["active"]),
            categories=json.loads(r.get("categories") or "[]"),
            min_relevance=r["min_relevance"],
        )
        await self._exec("DELETE FROM users WHERE unsubscribe_token=?", (token,))
        return user

    async def log_digest(self, email: str, article_count: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO digest_log (sent_at,recipient_email,article_count,status) "
            "VALUES (?,?,?,?)",
            (now, email, article_count, status)
        )

    def _to_dict(self, row: Row) -> dict:
        d = dict(row)
        d["category"] = _normalise_category(d.get("category", ""), d.get("source", ""))
        d["is_product_or_tool"] = bool(d.get("is_product_or_tool", 0))
        for f in ("tags", "competitors"):
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    d[f] = []
            else:
                d[f] = []  # always a list, never None
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
