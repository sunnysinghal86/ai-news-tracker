"""
digest_curator.py — Editorial digest curation engine

Implements the 7 digest quality improvements:
1. Signal over volume — adaptive article count based on story importance
2. Story clustering — group articles about the same event
3. "Why this matters" — platform engineer implication per article
4. Trend detection — surface recurring topics across digests
5. Engagement loop — (foundation for future click tracking)
6. Sleeper pick — one high-novelty lower-scored article
7. Negative selection — filter out low-substance posts

Called by main.py before send_daily_digest().
"""

import os
import re
import json
import logging
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


# ── 7. Negative selection filters ────────────────────────────────────────────
# Patterns that indicate low-substance posts worth filtering out

NOISE_PATTERNS = [
    r"(?i)^we('re| are) (hiring|looking for|excited to announce)",
    r"(?i)\b(round up|recap|weekly digest|newsletter issue)\b",
    r"(?i)\b(raises \$\d+[MB])\b(?!.*\b(product|launch|releases|open.source)\b)",
    r"(?i)^opinion[:\s]",
    r"(?i)\b(what (is|are) (ai|llm|machine learning))\b",  # 101-level explainers
]

def is_low_substance(article: dict) -> bool:
    """Returns True if article is likely noise — funding-only, 101 explainers etc."""
    title   = article.get("title", "")
    summary = article.get("summary", "")
    text    = f"{title} {summary}".lower()

    # Pure funding round with no product substance
    if re.search(r"\$\d+[mb] (series|round|funding)", text):
        if not re.search(r"(product|launch|release|open.source|model|api|tool)", text):
            return True

    # Pattern matches
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, title):
            return True

    # Very short summary — likely enrichment failed and article is thin
    if len(summary) < 60:
        return True

    return False


# ── 2. Story clustering ───────────────────────────────────────────────────────

def cluster_stories(articles: List[dict]) -> List[dict]:
    """
    Group articles that cover the same story.
    Returns one article per story (highest scored) with 'also_covered_by' list.
    Simple approach: shared keywords in title (≥2 significant words in common).
    """
    STOPWORDS = {"the","a","an","in","of","for","and","or","to","is","are",
                 "on","at","by","from","with","how","why","what","this","that",
                 "new","ai","llm","model","using","building","best"}

    def sig_words(title: str) -> set:
        return {w.lower() for w in re.findall(r'\b[a-z]{4,}\b', title.lower())
                if w.lower() not in STOPWORDS}

    clusters = []
    used = set()

    for i, a in enumerate(articles):
        if i in used:
            continue
        group = [a]
        words_i = sig_words(a["title"])
        for j, b in enumerate(articles):
            if j <= i or j in used:
                continue
            words_j = sig_words(b["title"])
            if len(words_i & words_j) >= 2:
                group.append(b)
                used.add(j)
        used.add(i)

        # Primary = highest relevance score in group
        primary = max(group, key=lambda x: x.get("relevance_score", 0))
        others  = [x for x in group if x["id"] != primary["id"]]
        if others:
            primary = dict(primary)
            primary["also_covered_by"] = [
                {"source": x["source"], "url": x["url"]} for x in others
            ]
        clusters.append(primary)

    return clusters


# ── 3. "Why this matters" context via Claude ──────────────────────────────────

async def add_implications(articles: List[dict], session: aiohttp.ClientSession) -> List[dict]:
    """
    Use Claude to add a one-liner platform-engineer implication per article.
    Batched in a single call to save tokens.
    """
    if not ANTHROPIC_API_KEY or not articles:
        return articles

    # Build batch prompt
    items = "\n".join([
        f"{i+1}. [{a.get('category','')}] {a['title']}: {a.get('summary','')[:200]}"
        for i, a in enumerate(articles)
    ])

    prompt = (
        "For each article below, write ONE sentence starting with 'For platform engineers:' "
        "that explains the practical implication — not a summary, but what action or "
        "decision this might affect. Be specific. If not relevant, write 'N/A'.\n\n"
        f"{items}\n\n"
        "Return ONLY a JSON array of strings in order, e.g. "
        '["For platform engineers: ...", "N/A", ...]'
    )

    try:
        payload = {
            "model": CLAUDE_MODEL,
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                return articles
            data = await resp.json()
            raw  = data["content"][0]["text"].strip()
            # Strip markdown fences
            raw  = re.sub(r"```json|```", "", raw).strip()
            implications = json.loads(raw)

        for i, article in enumerate(articles):
            if i < len(implications) and implications[i] != "N/A":
                articles[i] = dict(article)
                articles[i]["implication"] = implications[i]
    except Exception as e:
        logger.warning(f"Implication generation failed: {e}")

    return articles


# ── 4. Trend detection ────────────────────────────────────────────────────────

async def detect_trends(articles: List[dict], db) -> List[str]:
    """
    Look at last 14 days of digests and surface recurring themes.
    Returns list of trend strings like "AI agents in CI/CD (4 digests)".
    Simple: count tag frequency across recent articles.
    """
    try:
        recent = await db._query(
            "SELECT tags FROM articles "
            "WHERE fetched_at >= datetime('now', '-14 days') "
            "AND summary IS NOT NULL AND LENGTH(summary) > 40"
        )
        tag_counts = {}
        for row in recent:
            tags = json.loads(row.get("tags") or "[]")
            for t in tags:
                if len(t) > 3:  # skip short tags
                    tag_counts[t] = tag_counts.get(t, 0) + 1

        # Surface tags appearing 4+ times
        trends = [
            f"{tag.replace('-', ' ').title()} ({count} recent articles)"
            for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
            if count >= 4
        ][:3]
        return trends
    except Exception as e:
        logger.warning(f"Trend detection failed: {e}")
        return []


# ── 6. Sleeper pick ───────────────────────────────────────────────────────────

def find_sleeper(all_articles: List[dict], selected_ids: set) -> Optional[dict]:
    """
    Find one high-novelty article not in the main selection.
    Criteria: relevance 5-7 (not already top-scored), from a less-common source,
    has a non-empty summary, not noise.
    """
    mainstream = {"Medium", "OpenAI Blog", "NewsAPI"}
    candidates = [
        a for a in all_articles
        if a["id"] not in selected_ids
        and 5 <= a.get("relevance_score", 0) <= 7
        and a.get("source") not in mainstream
        and len(a.get("summary", "")) > 80
        and not is_low_substance(a)
    ]
    if not candidates:
        # Relax source constraint
        candidates = [
            a for a in all_articles
            if a["id"] not in selected_ids
            and 5 <= a.get("relevance_score", 0) <= 7
            and len(a.get("summary", "")) > 80
            and not is_low_substance(a)
        ]

    if candidates:
        sleeper = dict(candidates[0])
        sleeper["is_sleeper"] = True
        return sleeper
    return None


# ── 1. Adaptive article count ─────────────────────────────────────────────────

def adaptive_count(articles: List[dict]) -> int:
    """
    Return the right number of articles for this digest.
    Minimum 10 — subscribers expect a full briefing.
    Scales up to 14 on high-signal weeks.
    """
    scores = [a.get("relevance_score", 0) for a in articles]
    if not scores:
        return 10

    high_count = sum(1 for s in scores if s >= 8)

    if high_count >= 8:
        return 14  # very strong week — show more
    elif high_count >= 5:
        return 12  # solid week
    else:
        return 10  # minimum — always send at least 10


# ── Main curator entry point ──────────────────────────────────────────────────

async def curate_digest(
    articles: List[dict],
    db,
    session: aiohttp.ClientSession,
) -> dict:
    """
    Takes raw scored articles and returns a curated digest payload:
    {
      "stories":   [...],      # main articles, clustered + implications
      "sleeper":   {...},      # one under-the-radar pick
      "trends":    [...],      # recurring themes
      "article_count": N,
    }
    """
    if not articles:
        return {"stories": [], "sleeper": None, "trends": [], "article_count": 0}

    # Step 1 — filter noise
    clean = [a for a in articles if not is_low_substance(a)]
    logger.info(f"Digest curation: {len(articles)} → {len(clean)} after noise filter")

    # Step 2 — cluster into stories
    clustered = cluster_stories(clean)

    # Step 3 — adaptive count
    count = adaptive_count(clustered)
    main_stories = clustered[:count]

    # Step 4 — add "why this matters" implications via Claude
    main_stories = await add_implications(main_stories, session)

    # Step 5 — find sleeper pick from leftover articles
    selected_ids = {a["id"] for a in main_stories}
    sleeper = find_sleeper(articles, selected_ids)
    if sleeper:
        sleeper = (await add_implications([sleeper], session))[0]

    # Step 6 — detect trends
    trends = await detect_trends(articles, db)

    # Mark first story as the lead — highest scored after clustering
    if main_stories:
        main_stories[0] = dict(main_stories[0])
        main_stories[0]["is_lead"] = True

    return {
        "stories":       main_stories,
        "sleeper":       sleeper,
        "trends":        trends,
        "article_count": len(main_stories) + (1 if sleeper else 0),
    }
