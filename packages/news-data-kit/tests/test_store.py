"""Tests for SQLite store and queries."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from news_data_kit.types import NewsItem, NewsQuery
from news_data_kit.store.engine import NewsStore
from news_data_kit.store.queries import query_items


def _make_item(title: str, url: str, **kwargs) -> NewsItem:
    defaults = dict(
        item_id=f"id_{hash(url) % 10000}",
        source_type="rss",
        source_name="Test",
        title=title,
        url=url,
        published_at=datetime.now(),
        fetched_at=datetime.now(),
        markets=["HK"],
        category="general",
        sentiment="neutral",
    )
    defaults.update(kwargs)
    return NewsItem(**defaults)


class TestNewsStore:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = Path(self._tmpdir) / "test.db"
        self._articles = Path(self._tmpdir) / "articles"
        self.store = NewsStore(self._db, self._articles)

    def teardown_method(self):
        self.store.close()

    def test_save_new_item(self):
        item = _make_item("Test Title", "https://example.com/1")
        assert self.store.save(item) is True
        assert self.store.count() == 1

    def test_save_duplicate_url(self):
        item1 = _make_item("Title 1", "https://example.com/1")
        item2 = _make_item("Title 2", "https://example.com/1")
        self.store.save(item1)
        assert self.store.save(item2) is False
        assert self.store.count() == 1

    def test_save_duplicate_title(self):
        item1 = _make_item("Same exact title here", "https://a.com/1")
        item2 = _make_item("Same exact title here!", "https://b.com/2")
        self.store.save(item1)
        assert self.store.save(item2) is False

    def test_save_batch(self):
        items = [
            _make_item(f"Title {i}", f"https://example.com/{i}")
            for i in range(5)
        ]
        new_count = self.store.save_batch(items)
        assert new_count == 5
        assert self.store.count() == 5

    def test_is_duplicate_check(self):
        item = _make_item("Test", "https://example.com/1")
        self.store.save(item)
        assert self.store.is_duplicate("https://example.com/1", "Anything") is True
        assert self.store.is_duplicate("https://new.com", "Test") is True  # same title
        assert self.store.is_duplicate("https://new.com", "Different") is False

    def test_cleanup(self):
        old_item = _make_item("Old", "https://old.com",
                              published_at=datetime.now() - timedelta(days=60))
        new_item = _make_item("New", "https://new.com")
        self.store.save(old_item)
        self.store.save(new_item)
        assert self.store.count() == 2
        removed = self.store.cleanup(retention_days=30)
        assert removed >= 1
        assert self.store.count() == 1


class TestQueries:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = Path(self._tmpdir) / "test.db"
        self._articles = Path(self._tmpdir) / "articles"
        self.store = NewsStore(self._db, self._articles)
        # Seed data
        items = [
            _make_item("Macro news", "https://a.com/1", category="macro", markets=["CN"], sentiment="negative"),
            _make_item("Earnings beat", "https://a.com/2", category="earnings", markets=["US"], sentiment="positive"),
            _make_item("HK policy", "https://a.com/3", category="policy", markets=["HK"]),
        ]
        self.store.save_batch(items)

    def teardown_method(self):
        self.store.close()

    def test_query_by_market(self):
        items = query_items(self.store._conn, NewsQuery(markets=["CN"]))
        assert len(items) == 1
        assert items[0].category == "macro"

    def test_query_by_category(self):
        items = query_items(self.store._conn, NewsQuery(categories=["earnings"]))
        assert len(items) == 1
        assert items[0].title == "Earnings beat"

    def test_query_by_sentiment(self):
        items = query_items(self.store._conn, NewsQuery(sentiment="positive"))
        assert len(items) == 1

    def test_query_all(self):
        items = query_items(self.store._conn, NewsQuery())
        assert len(items) == 3

    def test_query_limit(self):
        items = query_items(self.store._conn, NewsQuery(limit=2))
        assert len(items) == 2

    def test_query_multiple_markets(self):
        items = query_items(self.store._conn, NewsQuery(markets=["CN", "US"]))
        assert len(items) == 2
