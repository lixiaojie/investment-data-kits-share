"""Standalone public news pipeline; initialization performs no network access."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from importlib import import_module, util

from . import config
from .clean import clean_item, is_advertorial
from .config import NewsKitConfig, get_config
from .store.engine import NewsStore
from .tagger import init_tagger, tag_batch
from .types import NewsItem, NewsQuery

__version__ = "0.2.1+share.1"
_PROVIDERS = {
    "rss": ("rss", "RSSProvider", "feedparser"),
    "akshare": ("akshare", "AkshareNewsProvider", "akshare"),
    "yfinance": ("yfinance", "YFinanceNewsProvider", "yfinance"),
    "finviz": ("finviz", "FinvizNewsProvider", "finvizfinance"),
}
_instances = {}
_last_run = {}


def init(**kwargs):
    cfg = NewsKitConfig(**kwargs)
    unknown = set(cfg.providers) - set(_PROVIDERS)
    if unknown:
        raise ValueError(f"Unknown providers: {sorted(unknown)}")
    reset()
    return config.init(**kwargs)


def reset():
    _instances.clear()
    _last_run.clear()
    init_tagger()
    config.reset()


def _store():
    cfg = get_config()
    cfg.ensure_dirs()
    return NewsStore(cfg.db_path, cfg.articles_dir)


def _matches(text, term):
    if re.fullmatch(r"[A-Za-z0-9.]+", term):
        return re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I) is not None
    return term.casefold() in text.casefold()


def _utc_naive(dt):
    # Adapters retain source timezones; RSS and synthetic naive timestamps are UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def fetch(markets=None, symbols=None, keywords=None, days=1, max_items=200, lang="any"):
    """Fetch, clean, tag and persist. Return newly inserted articles only.

    Empty results alone do not prove source availability. Inspect run_doctor()
    for per-provider errors, no-results and the last observed retrieval time.
    """
    if days < 1 or max_items < 1 or lang not in {"any", "en", "zh"}:
        raise ValueError("days/max_items must be positive and lang must be any/en/zh")
    if isinstance(keywords, str):
        keywords = [keywords]
    cfg = get_config()
    requested_markets = [m.upper() for m in markets] if markets else None
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    raw_items = []
    _last_run.clear()
    for provider_name in cfg.providers:
        module, cls, dep = _PROVIDERS[provider_name]
        if util.find_spec(dep) is None:
            _last_run[provider_name] = {"status": "dependency_missing", "package": dep}
            continue
        try:
            provider = _instances.get(provider_name)
            if provider is None:
                provider = getattr(import_module(f".providers.{module}", __name__), cls)()
                _instances[provider_name] = provider
            if lang != "any" and lang not in provider.SUPPORTED_LANGS:
                _last_run[provider_name] = {"status": "language_skipped"}
                continue
            args = dict(markets=requested_markets, symbols=symbols, keywords=keywords,
                        since=since, max_items=max_items)
            if provider_name == "rss":
                args["lang"] = lang
            items = provider.fetch(**args)
            errors = getattr(provider, "last_errors", [])
            # Optional adapters can swallow upstream failures; zero items is unknown.
            state = "partial" if errors else ("ok" if items else "no_results")
            _last_run[provider_name] = {"status": state, "raw_items": len(items),
                                       "checked_at": datetime.now(timezone.utc).isoformat(), "errors": errors}
            raw_items.extend(items)
        except Exception as exc:
            _last_run[provider_name] = {"status": "error", "error": type(exc).__name__}

    accepted = []
    for item in raw_items:
        if item.source_type != "rss":
            item.published_at = _utc_naive(item.published_at)
        item.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        item.metadata["timestamp_timezone"] = "UTC"
        if item.published_at < since or is_advertorial(item.title, item.summary):
            continue
        item.title, item.summary, _ = clean_item(item.title, item.summary, None)
        item.full_text = None  # This edition stores metadata and summaries, not article bodies.
        haystack = f"{item.title} {item.summary}"
        if not item.title or (keywords and not any(_matches(haystack, k) for k in keywords)):
            continue
        if symbols:
            matched = []
            for symbol in symbols:
                code = symbol.split(".", 1)[-1]
                terms = [code, *cfg.company_names.get(symbol, [])]
                if symbol in item.symbols or any(_matches(haystack, term) for term in terms):
                    matched.append(symbol)
            if not matched:
                continue
            item.symbols = sorted(set(item.symbols + matched))
        accepted.append(item)
    tagged = tag_batch(accepted)
    tagged.sort(key=lambda item: item.published_at, reverse=True)
    store = _store()
    inserted = []
    try:
        for item in tagged:
            if store.save(item):
                inserted.append(item)
            if len(inserted) >= max_items:
                break
    finally:
        store.close()
    # Persist aggregate retrieval status, never raw responses or credentials.
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=cfg.data_root, prefix="health-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(_last_run, out)
        os.replace(tmp, cfg.data_root / "health.json")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return inserted


def query(q=None, **kwargs):
    from .store.queries import query_items
    q = q if q is not None else NewsQuery(**kwargs)
    if q.limit < 1:
        raise ValueError("limit must be positive")
    store = _store()
    try:
        return query_items(store._conn, q)
    finally:
        store.close()


def search(text, limit=20):
    return query(NewsQuery(keywords=[text], limit=limit))


def refresh(markets=None):
    return len(fetch(markets=markets, max_items=500))


def cleanup():
    store = _store()
    try:
        return store.cleanup(get_config().retention_days)
    finally:
        store.close()


def run_doctor():
    cfg = get_config()
    history = {}
    try:
        history = json.loads((cfg.data_root / "health.json").read_text())
    except (FileNotFoundError, ValueError):
        pass
    states = {name: {"dependency_installed": util.find_spec(_PROVIDERS[name][2]) is not None,
                     "last_fetch": _last_run.get(name, history.get(name, {"status": "not_checked"}))}
              for name in cfg.providers}
    return {"providers": states, "note": "Last fetch observations; not a current connectivity guarantee"}


def run_doctor_report():
    return json.dumps(run_doctor(), ensure_ascii=False, indent=2)


def list_providers():
    return [{"name": name, **state} for name, state in run_doctor()["providers"].items()]
