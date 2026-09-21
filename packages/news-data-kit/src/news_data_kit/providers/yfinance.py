"""Yahoo Finance news provider for US stocks.

Uses yfinance .news property per symbol.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..cache import FileCache
from ..config import get_config
from ..dedup import item_id_from_url
from ..types import NewsItem

logger = logging.getLogger(__name__)


class YFinanceNewsProvider:
    """Yahoo Finance per-stock news."""

    name = "yfinance"
    SUPPORTED_LANGS: frozenset[str] = frozenset({"en"})

    def __init__(self) -> None:
        self._cache = FileCache(get_config().cache_dir, default_ttl=1800)
        try:
            import yfinance  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
            logger.info("yfinance not installed, YFinanceNewsProvider unavailable")

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

        # Only serves US market
        target = set(m.upper() for m in (markets or ["US"]))
        if "US" not in target:
            return []

        if not symbols:
            return []

        import yfinance as yf

        all_items: list[NewsItem] = []
        max_per = max(3, max_items // len(symbols))

        rate_limited = False
        for sym in symbols[:6]:
            if rate_limited:
                break

            # Convert to yfinance format (US.AAPL → AAPL)
            yf_sym = sym.split(".")[-1] if sym.startswith("US.") else sym

            cache_key = f"yfnews_{yf_sym}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                all_items.extend(_dicts_to_items(cached))
                continue

            try:
                t = yf.Ticker(yf_sym)
                raw: list[dict[str, Any]] = []
                for entry in (t.news or [])[:max_per]:
                    content = entry.get("content", {})
                    title = content.get("title", "")
                    if not title:
                        continue
                    url_info = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                    raw.append({
                        "title": title,
                        "url": url_info.get("url", ""),
                        "summary": content.get("summary", ""),
                        "source_name": content.get("provider", {}).get("displayName", "Yahoo Finance"),
                        "published_at": content.get("pubDate", ""),
                        "symbols": [sym],
                    })
                if raw:
                    self._cache.set(cache_key, raw)
                all_items.extend(_dicts_to_items(raw))
            except Exception as exc:
                exc_name = type(exc).__name__
                if "RateLimit" in exc_name or "TooManyRequests" in exc_name or "429" in str(exc):
                    logger.warning("yfinance rate-limited, skipping remaining symbols: %s", exc)
                    rate_limited = True
                    raise  # propagate to circuit breaker in registry
                logger.debug("yfinance news for %s failed: %s", yf_sym, exc)

        return all_items[:max_items]

    def healthcheck(self) -> bool:
        if not self._available:
            return False
        try:
            import yfinance as yf
            t = yf.Ticker("AAPL")
            _ = t.news
            return True
        except Exception:
            return False


def _dicts_to_items(raw_list: list[dict[str, Any]]) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    items = []
    for raw in raw_list:
        pub_str = raw.get("published_at", "")
        try:
            published_at = datetime.fromisoformat(pub_str) if pub_str else now
        except ValueError:
            published_at = now

        items.append(NewsItem(
            item_id=item_id_from_url("yfinance", raw.get("url", "") or raw.get("title", "")),
            source_type="yfinance",
            source_name=raw.get("source_name", "Yahoo Finance"),
            title=raw.get("title", ""),
            url=raw.get("url", ""),
            published_at=published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc),
            fetched_at=now,
            summary=raw.get("summary", ""),
            language="en",
            markets=["US"],
            symbols=raw.get("symbols", []),
        ))
    return items
