"""Bounded HTTP RSS fetching; parse downloaded bytes rather than ambient URLs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib.resources import files
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import feedparser

from ..clean import strip_html
from ..config import get_config
from ..dedup import item_id_from_url
from ..types import NewsItem


def load_feeds():
    path = get_config().feeds_config
    text = path.read_text(encoding="utf-8") if path else files("news_data_kit").joinpath("resources/feeds.json").read_text(encoding="utf-8")
    feeds = json.loads(text)
    if not isinstance(feeds, list):
        raise ValueError("Feed configuration must be a JSON array")
    for feed in feeds:
        if not isinstance(feed, dict) or urlparse(feed.get("url", "")).scheme not in {"http", "https"}:
            raise ValueError("Each feed must contain an HTTP(S) URL")
    return feeds


def _date(entry):
    for field in ("published", "updated"):
        raw = entry.get(field)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None), False
    return datetime.now(timezone.utc).replace(tzinfo=None), True


class RSSProvider:
    name = "rss"
    SUPPORTED_LANGS = frozenset({"en", "zh"})

    def fetch(self, markets=None, symbols=None, keywords=None, since=None, max_items=50, lang="any"):
        items = []
        self.last_errors = []
        self.last_successful_feeds = 0
        for feed in load_feeds():
            if markets and not set(markets).intersection(feed.get("markets", ["CN", "HK", "US"])):
                continue
            if lang != "any" and feed.get("language", "en") != lang:
                continue
            try:
                req = Request(feed["url"], headers={"User-Agent": "news-data-kit-share/0.2"})
                with urlopen(req, timeout=get_config().request_timeout) as response:
                    content = response.read(2_000_001)
                if len(content) > 2_000_000:
                    raise ValueError("RSS response exceeds 2 MB")
                parsed = feedparser.parse(content)
                if not parsed.get("version"):
                    raise ValueError("Response is not RSS or Atom")
                self.last_successful_feeds += 1
                for entry in parsed.entries:
                    published, inferred = _date(entry)
                    if since and published < since:
                        continue
                    title = strip_html(entry.get("title", ""))
                    url = entry.get("link", "")
                    if not title or urlparse(url).scheme not in {"http", "https"}:
                        continue
                    items.append(NewsItem(
                        item_id=item_id_from_url("rss", url), source_type="rss",
                        source_name=feed.get("name", "RSS"), title=title, url=url,
                        published_at=published, fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        summary=strip_html(entry.get("summary", ""))[:500],
                        language=feed.get("language", "en"), markets=list(feed.get("markets", [])),
                        metadata={"published_at_inferred": inferred, "timestamp_timezone": "UTC"},
                    ))
            except Exception as exc:
                self.last_errors.append({"feed": feed.get("name", "RSS"), "error": type(exc).__name__})
        if self.last_errors and not self.last_successful_feeds:
            raise RuntimeError("All selected RSS feeds failed")
        return items[:max_items]
