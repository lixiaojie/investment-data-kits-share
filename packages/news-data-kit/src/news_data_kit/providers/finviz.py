"""FinViz news provider for US stocks.

Scrapes FinViz.com for general market news and per-symbol news.
No API key required. Uses finvizfinance library.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from ..cache import FileCache
from ..config import get_config
from ..dedup import item_id_from_url
from ..types import NewsItem

logger = logging.getLogger(__name__)


class FinvizNewsProvider:
    """US stock news via FinViz scraping."""

    name = "finviz"
    SUPPORTED_LANGS: frozenset[str] = frozenset({"en"})

    def __init__(self) -> None:
        self._cache = FileCache(get_config().cache_dir, default_ttl=1800)
        try:
            import finvizfinance  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
            logger.info("finvizfinance not installed, FinvizNewsProvider unavailable")

    def fetch(
        self,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
        keywords: list[str] | None = None,
        since: datetime | None = None,
        max_items: int = 50,
    ) -> list[NewsItem]:
        if not self._available:
            return []

        target = set(m.upper() for m in (markets or ["US"]))
        if "US" not in target:
            return []

        all_items: list[NewsItem] = []

        # General market news
        all_items.extend(self._fetch_general(max_items))

        # Per-symbol news
        if symbols:
            all_items.extend(self._fetch_symbol_news(symbols, max_per=5))

        return all_items[:max_items]

    def _fetch_general(self, max_items: int = 30) -> list[NewsItem]:
        cached = self._cache.get("finviz_general")
        if cached is not None:
            return _dicts_to_items(cached)

        from finvizfinance.news import News

        try:
            fnews = News()
            all_news = fnews.get_news()
        except Exception as exc:
            logger.warning("finviz general news failed: %s", exc)
            return []

        items_raw: list[dict[str, Any]] = []
        # Only use 'news' key (skip 'blogs' — lower quality)
        df = all_news.get("news")
        if df is not None:
            for _, row in df.head(max_items).iterrows():
                title = str(row.get("Title", "")).strip()
                if not title:
                    continue
                items_raw.append({
                    "title": title,
                    "url": str(row.get("Link", "")),
                    "source_name": str(row.get("Source", "FinViz")),
                    "published_at": _parse_finviz_date(row.get("Date")),
                })

        if items_raw:
            self._cache.set("finviz_general", items_raw)

        return _dicts_to_items(items_raw)

    def _fetch_symbol_news(self, symbols: list[str], max_per: int = 5) -> list[NewsItem]:
        from finvizfinance.quote import finvizfinance

        items: list[NewsItem] = []

        for sym in symbols[:6]:
            ticker = sym.split(".")[-1] if sym.startswith("US.") else sym

            cache_key = f"finviz_{ticker}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                items.extend(_dicts_to_items(cached))
                continue

            try:
                stock = finvizfinance(ticker)
                df = stock.ticker_news()
                raw: list[dict[str, Any]] = []
                for _, row in df.head(max_per).iterrows():
                    title = str(row.get("Title", "")).strip()
                    if not title:
                        continue
                    raw.append({
                        "title": title,
                        "url": str(row.get("Link", "")),
                        "source_name": str(row.get("Source", "FinViz")),
                        "published_at": _parse_finviz_date(row.get("Date")),
                        "symbols": [sym],
                    })
                if raw:
                    self._cache.set(cache_key, raw)
                items.extend(_dicts_to_items(raw))
            except Exception as exc:
                logger.debug("finviz news for %s failed: %s", ticker, exc)

        return items

    def healthcheck(self) -> bool:
        if not self._available:
            return False
        try:
            from finvizfinance.news import News
            News().get_news()
            return True
        except Exception:
            return False


_FINVIZ_DATE_FORMATS = [
    "%b-%d-%y",       # "Apr-11-26"
    "%b-%d-%Y",       # "Apr-11-2026"
    "%b %d, %Y",      # "Apr 11, 2026"
    "%Y-%m-%d",       # "2026-04-11"
]

_FINVIZ_TIME_FORMATS = [
    "%I:%M%p",        # "11:15AM"
    "%I:%M %p",       # "11:15 AM"
    "%H:%M",          # "14:30"
]


def _parse_finviz_date(date_val: Any) -> str:
    """Parse FinViz date formats to ISO string."""
    if date_val is None:
        return ""
    if hasattr(date_val, "isoformat"):
        return date_val.isoformat()
    s = str(date_val).strip()
    if not s:
        return ""
    if "T" in s:
        return s

    today = datetime.now(ZoneInfo("America/New_York")).date()

    for fmt in _FINVIZ_TIME_FORMATS:
        try:
            t = datetime.strptime(s, fmt).time()
            return datetime.combine(today, t).isoformat()
        except ValueError:
            continue

    for fmt in _FINVIZ_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue

    return s


def _dicts_to_items(raw_list: list[dict[str, Any]]) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    items = []
    for raw in raw_list:
        pub_str = raw.get("published_at", "")
        try:
            published_at = datetime.fromisoformat(pub_str) if pub_str else now
        except (ValueError, TypeError):
            published_at = now

        items.append(NewsItem(
            item_id=item_id_from_url("finviz", raw.get("url", "") or raw.get("title", "")),
            source_type="finviz",
            source_name=raw.get("source_name", "FinViz"),
            title=raw.get("title", ""),
            url=raw.get("url", ""),
            published_at=published_at if published_at.tzinfo else published_at.replace(tzinfo=ZoneInfo("America/New_York")),
            fetched_at=now,
            language="en",
            markets=["US"],
            symbols=raw.get("symbols", []),
        ))
    return items
