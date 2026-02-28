"""
Database - async SQLite via aiosqlite
"""

import aiosqlite
import json
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/tmp/news_tracker.db")


@dataclass
class User:
    id: Optional[int]
    email: str
    name: str
    active: bool = True
    categories: Optional[List[str]] = None
    min_relevance: int = 5

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "active": self.active,
            "categories": self.categories or [],
            "min_relevance": self.min_relevance,
        }


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db = None

    async def connect(self):
        # Safely create parent directory only if one exists in the path
        parent = os.path.dirname(self.path)
        if parent and parent != "/" and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
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
                url TEXT NOT NULL,
                source TEXT,
                published_at TEXT,
                author TEXT,
                score INTEGER DEFAULT 0,
                summary TEXT,
                category TEXT,
                tags TEXT,
                relevance_score INTEGER DEFAULT 5,
                is_product_or_tool INTEGER DEFAULT 0,
                product_name TEXT,
                competitors TEXT,
                competitive_advantage TEXT,
                fetched_at TEXT NOT NULL,
                emailed INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                active INTEGER DEFAULT 1,
                categories TEXT,
                min_relevance INTEGER DEFAULT 5,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS digest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                article_count INTEGER,
                status TEXT
            );
        """)
        await self._db.commit()

    async def upsert_articles(self, articles: list):
        now = datetime.now(timezone.utc).isoformat()
        for a in articles:
            pub = (
                a.published_at
                if isinstance(a.published_at, str)
                else a.published_at.isoformat()
            )
            await self._db.execute(
                """
                INSERT INTO articles (
                    id, title, url, source, published_at, author, score,
                    summary, category, tags, relevance_score,
                    is_product_or_tool, product_name, competitors,
                    competitive_advantage, fetched_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    summary=excluded.summary,
                    category=excluded.category,
                    tags=excluded.tags,
                    relevance_score=excluded.relevance_score,
                    is_product_or_tool=excluded.is_product_or_tool,
                    product_name=excluded.product_name,
                    competitors=excluded.competitors,
                    competitive_advantage=excluded.competitive_advantage,
                    fetched_at=excluded.fetched_at
                """,
                (
                    a.id, a.title, a.url, a.source, pub,
                    a.author, a.score, a.summary, a.category,
                    json.dumps(a.tags or []), a.relevance_score,
                    1 if a.is_product_or_tool else 0,
                    a.product_name,
                    json.dumps(a.competitors or []),
                    a.competitive_advantage, now,
                ),
            )
        await self._db.commit()
        logger.info(f"Upserted {len(articles)} articles")

    async def get_articles(
        self, limit=50, offset=0, category=None,
        source=None, min_relevance=0, search=None,
    ) -> List[dict]:
        conditions = ["1=1"]
        params: list = []
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
        params.extend([limit, offset])
        async with self._db.execute(
            f"SELECT * FROM articles WHERE {where} "
            f"ORDER BY relevance_score DESC, fetched_at DESC LIMIT ? OFFSET ?",
            params,
        ) as cur:
            rows = await cur.fetchall()
        return [self._to_dict(r) for r in rows]

    async def get_top_articles(self, limit=10, min_relevance=5) -> List[dict]:
        async with self._db.execute(
            "SELECT * FROM articles WHERE relevance_score >= ? "
            "ORDER BY relevance_score DESC, score DESC LIMIT ?",
            (min_relevance, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._to_dict(r) for r in rows]

    async def get_stats(self) -> dict:
        async with self._db.execute("SELECT COUNT(*) as total FROM articles") as c:
            total = (await c.fetchone())["total"]
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

    async def create_user(
        self, email: str, name: str,
        categories=None, min_relevance: int = 5,
    ) -> "User":
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT OR IGNORE INTO users "
            "(email, name, active, categories, min_relevance, created_at) "
            "VALUES (?,?,1,?,?,?)",
            (email, name, json.dumps(categories or []), min_relevance, now),
        )
        await self._db.commit()
        return await self.get_user_by_email(email)

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
        )

    async def get_active_users(self) -> List["User"]:
        async with self._db.execute("SELECT * FROM users WHERE active=1") as c:
            rows = await c.fetchall()
        return [
            User(
                id=r["id"], email=r["email"], name=r["name"],
                active=True,
                categories=json.loads(r["categories"] or "[]"),
                min_relevance=r["min_relevance"],
            )
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
            (now, email, article_count, status),
        )
        await self._db.commit()

    def _to_dict(self, row) -> dict:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["competitors"] = json.loads(d.get("competitors") or "[]")
        d["is_product_or_tool"] = bool(d.get("is_product_or_tool"))
        return d


_db: Optional[Database] = None


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
