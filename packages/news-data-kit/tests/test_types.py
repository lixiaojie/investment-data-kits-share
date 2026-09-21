"""Tests for core types."""

from datetime import datetime
from news_data_kit.types import NewsItem, NewsQuery


def test_news_item_defaults():
    item = NewsItem(item_id="abc123", source_type="rss", source_name="Test", title="Title", url="https://example.com")
    assert item.language == "zh"
    assert item.category == "general"
    assert item.sentiment == "neutral"
    assert item.urgency == "normal"
    assert item.markets == []
    assert item.symbols == []
    assert item.tags == []


def test_news_query_defaults():
    q = NewsQuery()
    assert q.limit == 100
    assert q.markets is None
    assert q.since is None
