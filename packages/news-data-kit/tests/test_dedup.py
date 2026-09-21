"""Tests for deduplication engine."""

from news_data_kit.dedup import url_hash, title_hash, item_id_from_url, DedupEngine


def test_url_hash_deterministic():
    h1 = url_hash("https://example.com/article/123")
    h2 = url_hash("https://example.com/article/123")
    assert h1 == h2


def test_url_hash_normalizes_trailing_slash():
    h1 = url_hash("https://example.com/article/")
    h2 = url_hash("https://example.com/article")
    assert h1 == h2


def test_url_hash_case_insensitive():
    h1 = url_hash("https://Example.COM/Article")
    h2 = url_hash("https://example.com/article")
    assert h1 == h2


def test_title_hash_ignores_punctuation():
    h1 = title_hash("Fed raises rates by 25bp!")
    h2 = title_hash("Fed raises rates by 25bp")
    assert h1 == h2


def test_title_hash_case_insensitive():
    h1 = title_hash("BREAKING: Market Crash")
    h2 = title_hash("breaking: market crash")
    assert h1 == h2


def test_title_hash_chinese():
    h1 = title_hash("美联储加息25个基点")
    h2 = title_hash("美联储加息25个基点！")
    assert h1 == h2


def test_item_id_deterministic():
    id1 = item_id_from_url("rss", "https://example.com/1")
    id2 = item_id_from_url("rss", "https://example.com/1")
    assert id1 == id2
    assert len(id1) == 24


def test_item_id_differs_by_source():
    id1 = item_id_from_url("rss", "https://example.com/1")
    id2 = item_id_from_url("futu", "https://example.com/1")
    assert id1 != id2


class TestDedupEngine:
    def test_first_item_not_duplicate(self):
        engine = DedupEngine()
        assert not engine.is_duplicate("https://a.com", "Title A")

    def test_same_url_is_duplicate(self):
        engine = DedupEngine()
        engine.is_duplicate("https://a.com", "Title A")
        assert engine.is_duplicate("https://a.com", "Title B")

    def test_same_title_is_duplicate(self):
        engine = DedupEngine()
        engine.is_duplicate("https://a.com", "Fed raises rates by 25bp")
        assert engine.is_duplicate("https://b.com", "Fed raises rates by 25bp!")

    def test_different_items_not_duplicate(self):
        engine = DedupEngine()
        engine.is_duplicate("https://a.com", "Title A")
        assert not engine.is_duplicate("https://b.com", "Completely different title")

    def test_seen_count(self):
        engine = DedupEngine()
        engine.is_duplicate("https://a.com", "A")
        engine.is_duplicate("https://b.com", "B")
        engine.is_duplicate("https://a.com", "A again")  # dup
        assert engine.seen_count == 2
