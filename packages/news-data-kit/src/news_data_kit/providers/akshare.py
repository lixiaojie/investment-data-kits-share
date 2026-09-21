"""Akshare-based news provider for Chinese financial news.

Sources: 财联社 (CLS) + 东方财富 (Eastmoney) headlines + per-stock news.
Requires proxy cleanup for domestic China APIs.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ..cache import FileCache
from ..clean import is_advertorial
from ..config import get_config
from ..dedup import item_id_from_url
from ..types import NewsItem

logger = logging.getLogger(__name__)


def _import_akshare():
    """Respect the caller's configured networking."""
    import akshare
    return akshare


class AkshareNewsProvider:
    """Chinese financial news via akshare."""

    name = "akshare"
    SUPPORTED_LANGS: frozenset[str] = frozenset({"zh"})

    def __init__(self) -> None:
        self._cache = FileCache(get_config().cache_dir, default_ttl=1800)

    def fetch(
        self,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
        keywords: list[str] | None = None,
        since: datetime | None = None,
        max_items: int = 50,
    ) -> list[NewsItem]:
        # Only serves CN/HK markets
        target = set(m.upper() for m in (markets or ["CN"]))
        if not target.intersection({"CN", "SH", "SZ", "HK"}):
            return []

        all_items: list[NewsItem] = []

        # Market-wide financial news (CN)
        if target.intersection({"CN", "SH", "SZ"}):
            all_items.extend(self._fetch_cn_news(max_items))

        # Per-stock news
        if symbols:
            all_items.extend(self._fetch_stock_news(symbols, max_per=3))

        return all_items[:max_items]

    def _fetch_cn_news(self, max_items: int = 30) -> list[NewsItem]:
        cached = self._cache.get("akshare_cn_news")
        if cached is not None:
            return _dicts_to_items(cached)

        ak = _import_akshare()
        items_raw: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 财联社 telegrams
        try:
            df = ak.stock_info_global_cls()
            for _, row in df.iterrows():
                title = str(row.get("标题", "")).strip()
                if not title or title in seen:
                    continue
                if is_advertorial(title, str(row.get("内容", ""))):
                    continue
                seen.add(title)
                items_raw.append({
                    "title": title,
                    "summary": str(row.get("内容", ""))[:500],
                    "source_name": "财联社",
                    "url": "",
                    "published_at": f"{row.get('发布日期', '')} {row.get('发布时间', '')}".strip(),
                })
        except Exception as exc:
            logger.warning("akshare CLS news failed: %s", exc)

        # 东方财富 headlines
        try:
            df = ak.stock_info_global_em()
            for _, row in df.head(20).iterrows():
                title = str(row.get("标题", "")).strip()
                if not title or title in seen:
                    continue
                if is_advertorial(title, str(row.get("摘要", ""))):
                    continue
                seen.add(title)
                items_raw.append({
                    "title": title,
                    "summary": str(row.get("摘要", ""))[:500],
                    "source_name": "东方财富",
                    "url": str(row.get("链接", "")),
                    "published_at": str(row.get("发布时间", "")),
                })
        except Exception as exc:
            logger.warning("akshare EM news failed: %s", exc)

        # 同花顺 global news
        try:
            df = ak.stock_info_global_ths()
            for _, row in df.head(15).iterrows():
                title = str(row.get("标题", "")).strip()
                if not title or title in seen:
                    continue
                if is_advertorial(title, str(row.get("内容", ""))):
                    continue
                seen.add(title)
                items_raw.append({
                    "title": title,
                    "summary": str(row.get("内容", ""))[:500],
                    "source_name": "同花顺",
                    "url": str(row.get("链接", "")),
                    "published_at": str(row.get("发布时间", "")),
                })
        except Exception as exc:
            logger.warning("akshare THS news failed: %s", exc)

        if items_raw:
            self._cache.set("akshare_cn_news", items_raw)

        return _dicts_to_items(items_raw[:max_items])

    def _fetch_stock_news(self, symbols: list[str], max_per: int = 3) -> list[NewsItem]:
        """Per-stock news via eastmoney."""
        ak = _import_akshare()
        items: list[NewsItem] = []

        for sym in symbols[:8]:
            # Extract bare code (CN.600519 → 600519)
            bare = sym.split(".")[-1] if "." in sym else sym
            if not bare.isdigit():
                continue

            cache_key = f"akshare_stock_{bare}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                items.extend(_dicts_to_items(cached))
                continue

            try:
                df = ak.stock_news_em(symbol=bare)
                raw: list[dict[str, Any]] = []
                for _, row in df.head(max_per).iterrows():
                    title = str(row.get("新闻标题", "")).strip()
                    if not title:
                        continue
                    raw.append({
                        "title": title,
                        "summary": str(row.get("新闻内容", ""))[:500],
                        "source_name": f"东方财富/{bare}",
                        "url": str(row.get("新闻链接", "")),
                        "published_at": str(row.get("发布时间", "")),
                        "symbols": [sym],
                    })
                if raw:
                    self._cache.set(cache_key, raw)
                items.extend(_dicts_to_items(raw))
            except Exception as exc:
                logger.debug("akshare stock news for %s failed: %s", bare, exc)

        return items

    def healthcheck(self) -> bool:
        try:
            _import_akshare()
            return True
        except Exception:
            return False


def _dicts_to_items(raw_list: list[dict[str, Any]]) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    items = []
    for raw in raw_list:
        pub_str = str(raw.get("published_at", "")).strip()
        published_at = now
        if pub_str:
            try:
                published_at = datetime.fromisoformat(pub_str)
            except ValueError:
                # Try space-separated format: "2026-04-12 20:15:47"
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        published_at = datetime.strptime(pub_str, fmt)
                        break
                    except ValueError:
                        continue

        item = NewsItem(
            item_id=item_id_from_url("akshare", raw.get("url", "") or raw.get("title", "")),
            source_type="akshare",
            source_name=raw.get("source_name", "akshare"),
            title=raw.get("title", ""),
            url=raw.get("url", ""),
            published_at=published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone(timedelta(hours=8))),
            fetched_at=now,
            summary=raw.get("summary", ""),
            language="zh",
            markets=["CN"],
            symbols=raw.get("symbols", []),
        )
        items.append(item)
    return items
