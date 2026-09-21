"""Core data types for news-data-kit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsItem:
    """A single news article with metadata and tags."""

    # ── Identity ──
    item_id: str                   # SHA256(source_type + ":" + url)
    source_type: str               # "rss" | "futu" | "akshare" | "yfinance" | "telegram"
    source_name: str               # "BBC Business" | "财联社" | "Futu HK"

    # ── Content ──
    title: str
    url: str
    author: str = ""
    published_at: datetime = field(default_factory=datetime.now)
    fetched_at: datetime = field(default_factory=datetime.now)
    summary: str = ""              # Cleaned first 500 chars
    full_text: str | None = None   # Full article text (stored in Parquet)

    # ── Tags (populated by tagger) ──
    language: str = "zh"           # "zh" | "en"
    markets: list[str] = field(default_factory=list)      # ["HK", "CN"]
    symbols: list[str] = field(default_factory=list)      # ["CN.600519"]
    category: str = "general"      # macro | earnings | policy | sector | company | commodity | general
    sentiment: str = "neutral"     # positive | negative | neutral
    urgency: str = "normal"        # breaking | normal
    tags: list[str] = field(default_factory=list)          # Free-form tags

    # ── Extension ──
    metadata: dict = field(default_factory=dict)


@dataclass
class NewsQuery:
    """Query parameters for news store lookups."""

    markets: list[str] | None = None
    symbols: list[str] | None = None
    categories: list[str] | None = None
    sentiment: str | None = None
    language: str | None = None
    source_types: list[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100
    keywords: list[str] | None = None
