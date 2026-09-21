import io
import json
from datetime import datetime, timezone
from email.utils import format_datetime

import pytest

import news_data_kit as ndk
from news_data_kit.providers import rss


def feeds(tmp_path):
    path = tmp_path / "feeds.json"
    path.write_text(json.dumps([{"url":"https://example.com/rss", "name":"Example", "markets":["US"]}]))
    ndk.init(feeds_config=path)


def response(monkeypatch, title="Apple reports strong revenue", date=None):
    dt = date or format_datetime(datetime.now(timezone.utc))
    xml = f'<rss version="2.0"><channel><title>Example</title><item><title>{title}</title><link>https://example.com/article</link><pubDate>{dt}</pubDate></item></channel></rss>'
    monkeypatch.setattr(rss, "urlopen", lambda *a, **k: io.BytesIO(xml.encode()))


def test_packaged_feeds_and_cold_health():
    ndk.init()
    assert len(rss.load_feeds()) == 2
    state = ndk.run_doctor()["providers"]["rss"]
    assert state["last_fetch"]["status"] == "not_checked"


def test_init_no_disk_or_network(tmp_path):
    ndk.init(data_root=tmp_path / "unused")
    assert not (tmp_path / "unused").exists()


def test_fetch_persists_dedup_across_restart(monkeypatch, tmp_path):
    feeds(tmp_path)
    response(monkeypatch)
    assert len(ndk.fetch(markets=["US"])) == 1
    ndk.reset()
    feeds(tmp_path)
    assert ndk.fetch(markets=["US"]) == []
    assert len(ndk.query()) == 1
    assert len(ndk.search("Apple")) == 1


def test_name_enrichment_is_explicit(monkeypatch, tmp_path):
    feeds(tmp_path)
    response(monkeypatch)
    assert ndk.fetch(symbols=["US.AAPL"]) == []
    path = ndk.get_config().feeds_config
    ndk.init(feeds_config=path, company_names={"US.AAPL":["Apple"]})
    result = ndk.fetch(symbols=["US.AAPL"])
    assert len(result) == 1 and "US.AAPL" in result[0].symbols


def test_symbols_do_not_match_substrings(monkeypatch, tmp_path):
    feeds(tmp_path)
    response(monkeypatch, title="META expands technology")
    assert ndk.fetch(symbols=["US.T"]) == []


def test_health_failure_is_real_observation(monkeypatch, tmp_path):
    feeds(tmp_path)
    monkeypatch.setattr(rss, "urlopen", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    assert ndk.fetch() == []
    assert ndk.run_doctor()["providers"]["rss"]["last_fetch"]["status"] == "error"
    ndk.reset()
    assert ndk.run_doctor()["providers"]["rss"]["last_fetch"]["status"] == "error"


def test_news_keyword_query_is_not_sql_pattern(monkeypatch, tmp_path):
    feeds(tmp_path)
    response(monkeypatch)
    ndk.fetch()
    assert ndk.search("%") == []


def test_bad_response_is_error_not_healthy_empty(monkeypatch, tmp_path):
    feeds(tmp_path)
    monkeypatch.setattr(rss, "urlopen", lambda *a, **k: io.BytesIO(b"<html>Denied</html>"))
    ndk.fetch()
    assert ndk.run_doctor()["providers"]["rss"]["last_fetch"]["status"] == "error"


def test_utc_date_parse_and_inferred_flag():
    dt, inferred = rss._date({"published":"Mon, 21 Sep 2026 10:00:00 +0800"})
    assert dt.hour == 2 and not inferred
    assert rss._date({})[1]


def test_unknown_provider_rejected(tmp_path):
    with pytest.raises(ValueError):
        ndk.init(providers=("unknown",), data_root=tmp_path / "unused")
    assert not (tmp_path / "unused").exists()


def test_yahoo_timezone_does_not_depend_on_machine():
    from datetime import timedelta
    from news_data_kit.providers.yfinance import _dicts_to_items
    expected = datetime.now(timezone.utc) - timedelta(hours=20)
    item = _dicts_to_items([{'title':'timezone example', 'published_at':expected.isoformat()}])[0]
    assert item.published_at.tzinfo is not None
    assert ndk._utc_naive(item.published_at) == expected.replace(tzinfo=None)


def test_asia_and_finviz_times_have_explicit_zones():
    from news_data_kit.providers.akshare import _dicts_to_items as ak
    from news_data_kit.providers.finviz import _dicts_to_items as fv
    a = ak([{'title':'example', 'published_at':'2026-09-21 10:00:00'}])[0]
    f = fv([{'title':'example', 'published_at':'2026-09-21 10:00:00'}])[0]
    assert ndk._utc_naive(a.published_at).hour == 2
    assert ndk._utc_naive(f.published_at).hour == 14


def test_distinct_url_less_articles_survive_restart(tmp_path):
    from news_data_kit.store.engine import NewsStore
    args = (tmp_path/'test.db', tmp_path/'articles')
    store = NewsStore(*args)
    a = ndk.NewsItem(item_id='a', source_type='akshare', source_name='CLS', title='First corporate earnings', url='')
    b = ndk.NewsItem(item_id='b', source_type='akshare', source_name='CLS', title='Second policy change', url='')
    assert store.save(a) and store.save(b)
    store.close()
    store = NewsStore(*args)
    assert not store.save(a)
    assert store.count() == 2
    store.close()


def test_cleanup_uses_utc_retention(tmp_path, monkeypatch):
    import time
    from datetime import timedelta
    from news_data_kit.store.engine import NewsStore
    previous = __import__('os').environ.get('TZ')
    monkeypatch.setenv('TZ', 'Asia/Shanghai')
    if hasattr(time, 'tzset'):
        time.tzset()
    try:
        store = NewsStore(tmp_path/'retention.db', tmp_path/'articles')
        item = ndk.NewsItem(item_id='recent',source_type='rss',source_name='Example',title='Still recent',url='https://example.com/recent',published_at=(datetime.now(timezone.utc)-timedelta(hours=20)).replace(tzinfo=None))
        assert store.save(item)
        assert store.cleanup(1) == 0
        store.close()
    finally:
        if previous is None:
            monkeypatch.delenv('TZ', raising=False)
        else:
            monkeypatch.setenv('TZ', previous)
        if hasattr(time, 'tzset'):
            time.tzset()
