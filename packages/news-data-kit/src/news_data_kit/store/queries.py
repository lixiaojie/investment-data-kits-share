"""Query interface for the news store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from ..types import NewsItem, NewsQuery


def query_items(conn: sqlite3.Connection, q: NewsQuery) -> list[NewsItem]:
    """Execute a NewsQuery against the SQLite store."""
    clauses: list[str] = []
    params: list[Any] = []

    if q.markets:
        # JSON array containment check — match any market
        market_clauses = []
        for m in q.markets:
            market_clauses.append("markets_json LIKE ?")
            params.append(f'%"{m}"%')
        clauses.append(f"({' OR '.join(market_clauses)})")

    if q.symbols:
        sym_clauses = []
        for s in q.symbols:
            sym_clauses.append("symbols_json LIKE ?")
            params.append(f'%"{s}"%')
        clauses.append(f"({' OR '.join(sym_clauses)})")

    if q.categories:
        placeholders = ",".join("?" for _ in q.categories)
        clauses.append(f"category IN ({placeholders})")
        params.extend(q.categories)

    if q.sentiment:
        clauses.append("sentiment = ?")
        params.append(q.sentiment)

    if q.keywords:
        clauses.append("(" + " OR ".join("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')" for _ in q.keywords) + ")")
        for keyword in q.keywords:
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.extend([f"%{escaped}%", f"%{escaped}%"])

    if q.language:
        clauses.append("language = ?")
        params.append(q.language)

    if q.source_types:
        placeholders = ",".join("?" for _ in q.source_types)
        clauses.append(f"source_type IN ({placeholders})")
        params.extend(q.source_types)

    if q.since:
        clauses.append("published_at >= ?")
        params.append(q.since.isoformat())

    if q.until:
        clauses.append("published_at <= ?")
        params.append(q.until.isoformat())

    where = " AND ".join(clauses) if clauses else "1=1"
    sql = f"SELECT * FROM news_items WHERE {where} ORDER BY published_at DESC LIMIT ?"
    params.append(q.limit)

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_item(row) for row in rows]


def _row_to_item(row: sqlite3.Row) -> NewsItem:
    """Convert a SQLite row to NewsItem."""
    return NewsItem(
        item_id=row["item_id"],
        source_type=row["source_type"],
        source_name=row["source_name"],
        title=row["title"],
        url=row["url"],
        author=row["author"],
        published_at=datetime.fromisoformat(row["published_at"]),
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        summary=row["summary"],
        full_text=None,  # fulltext in Parquet, not loaded by default
        language=row["language"],
        markets=json.loads(row["markets_json"]),
        symbols=json.loads(row["symbols_json"]),
        category=row["category"],
        sentiment=row["sentiment"],
        urgency=row["urgency"],
        tags=json.loads(row["tags_json"]),
        metadata=json.loads(row["metadata_json"]),
    )
