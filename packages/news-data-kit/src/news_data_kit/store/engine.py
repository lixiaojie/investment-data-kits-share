"""SQLite metadata store + Parquet fulltext store."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..dedup import title_hash, url_hash
from ..types import NewsItem

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news_items (
    item_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT DEFAULT '',
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    summary TEXT DEFAULT '',
    language TEXT DEFAULT 'zh',
    markets_json TEXT DEFAULT '[]',
    symbols_json TEXT DEFAULT '[]',
    category TEXT DEFAULT 'general',
    sentiment TEXT DEFAULT 'neutral',
    urgency TEXT DEFAULT 'normal',
    tags_json TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    has_fulltext INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_published ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_category ON news_items(category, published_at);
DROP INDEX IF EXISTS idx_url;
CREATE UNIQUE INDEX IF NOT EXISTS idx_url_nonempty ON news_items(url) WHERE url != '';

CREATE TABLE IF NOT EXISTS dedup_hashes (
    url_hash TEXT PRIMARY KEY,
    title_hash TEXT NOT NULL,
    item_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_title_hash ON dedup_hashes(title_hash);
"""


class NewsStore:
    """SQLite-backed news item store with Parquet fulltext support."""

    def __init__(self, db_path: Path, articles_dir: Path) -> None:
        self._db_path = db_path
        self._articles_dir = articles_dir
        self._articles_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def is_duplicate(self, url: str, title: str) -> bool:
        """Check if an item with same URL or similar title already exists."""
        if url.strip():
            uh = url_hash(url)
            row = self._conn.execute("SELECT 1 FROM dedup_hashes WHERE url_hash = ?", (uh,)).fetchone()
            if row:
                return True
        th = title_hash(title)
        row = self._conn.execute("SELECT 1 FROM dedup_hashes WHERE title_hash = ?", (th,)).fetchone()
        return row is not None

    def save(self, item: NewsItem) -> bool:
        """Save a news item. Returns True if new, False if duplicate.

        Also saves fulltext to Parquet if item.full_text is set.
        """
        if self.is_duplicate(item.url, item.title):
            return False

        try:
            cursor = self._conn.execute(
                """INSERT OR IGNORE INTO news_items
                   (item_id, source_type, source_name, title, url, author,
                    published_at, fetched_at, summary, language,
                    markets_json, symbols_json, category, sentiment, urgency,
                    tags_json, metadata_json, has_fulltext)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.item_id,
                    item.source_type,
                    item.source_name,
                    item.title,
                    item.url,
                    item.author,
                    item.published_at.isoformat(),
                    item.fetched_at.isoformat(),
                    item.summary,
                    item.language,
                    json.dumps(item.markets, ensure_ascii=False),
                    json.dumps(item.symbols, ensure_ascii=False),
                    item.category,
                    item.sentiment,
                    item.urgency,
                    json.dumps(item.tags, ensure_ascii=False),
                    json.dumps(item.metadata, ensure_ascii=False, default=str),
                    1 if item.full_text else 0,
                ),
            )
            if cursor.rowcount == 0:
                self._conn.rollback()
                return False
            # Dedup hashes
            self._conn.execute(
                "INSERT OR IGNORE INTO dedup_hashes (url_hash, title_hash, item_id) VALUES (?, ?, ?)",
                (url_hash(item.url) if item.url.strip() else "item:" + item.item_id, title_hash(item.title), item.item_id),
            )
            self._conn.commit()

            # Save fulltext to Parquet (append to daily file)
            if item.full_text:
                self._save_fulltext(item.item_id, item.full_text, item.published_at)

            return True

        except sqlite3.IntegrityError:
            return False
        except Exception as exc:
            logger.warning("Failed to save item %s: %s", item.item_id, exc)
            self._conn.rollback()
            return False

    def save_batch(self, items: list[NewsItem]) -> int:
        """Save multiple items. Returns count of new items saved."""
        new_count = 0
        for item in items:
            if self.save(item):
                new_count += 1
        return new_count

    def _save_fulltext(self, item_id: str, full_text: str, published_at: datetime) -> None:
        """Append fulltext to daily Parquet file."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            date_str = published_at.strftime("%Y-%m-%d")
            path = self._articles_dir / f"{date_str}.parquet"

            table = pa.table({"item_id": [item_id], "full_text": [full_text]})

            if path.exists():
                existing = pq.read_table(path)
                table = pa.concat_tables([existing, table])

            pq.write_table(table, path)
        except ImportError:
            # pyarrow not installed — skip fulltext storage
            logger.debug("pyarrow not installed, skipping fulltext storage")
        except Exception as exc:
            logger.debug("Fulltext save failed for %s: %s", item_id, exc)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM news_items").fetchone()
        return row[0] if row else 0

    def cleanup(self, retention_days: int = 30) -> int:
        """Remove items older than retention_days. Returns count removed."""
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = (now_utc - timedelta(days=retention_days)).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM news_items WHERE published_at < ?", (cutoff,)
        )
        removed = cursor.rowcount
        # Clean orphan dedup hashes
        self._conn.execute(
            "DELETE FROM dedup_hashes WHERE item_id NOT IN (SELECT item_id FROM news_items)"
        )
        self._conn.commit()

        # Clean old Parquet files
        cutoff_date = now_utc - timedelta(days=retention_days)
        for pq_file in self._articles_dir.glob("*.parquet"):
            try:
                file_date = datetime.strptime(pq_file.stem, "%Y-%m-%d")
                if file_date < cutoff_date:
                    pq_file.unlink()
                    removed += 1
            except ValueError:
                pass

        logger.info("Cleanup: removed %d items older than %d days", removed, retention_days)
        return removed
