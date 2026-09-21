"""Public-provider sharing edition. See README for API differences and data semantics."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import warnings
from datetime import date, datetime, timezone

import pandas as pd

from . import indicators, symbols
from .config import Config, get_config, init, reset
from .providers.base import ProviderUnavailableError
from .providers.registry import get_provider
from .symbols import normalize, market, exchange

__version__ = "0.5.2+share.1"


class StaleDataError(ProviderUnavailableError):
    """Only out-of-date data was available; opt in explicitly to return it."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _providers():
    cfg = get_config()
    return ("stub",) if cfg.use_stubs else cfg.providers


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value) if isinstance(value, str) else value


def _cache_path(symbol, days, end_date, adjust):
    # Include provider configuration and range: no cross-source or partial-range merges.
    key = json.dumps([symbol, days, str(end_date), adjust, _providers()])
    digest = hashlib.sha256(key.encode()).hexdigest()
    return get_config().data_root / "klines" / f"{digest}.parquet"


def _decorate(df, *, cached, end_date, days, max_age):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df.date <= end_date].sort_values("date").drop_duplicates("date").tail(days)
    if df.empty:
        raise ValueError("No rows in requested date range")
    as_of = df.date.max()
    df.attrs = {"provider": str(df["provider"].iloc[-1]), "as_of": as_of.isoformat(),
                "fetched_at": str(df["fetched_at"].iloc[-1]),
                "adjust": str(df["adjust"].iloc[-1]), "cache_hit": cached,
                "stale": (end_date - as_of).days > max_age,
                "requested_rows": days, "returned_rows": len(df), "complete": len(df) >= days,
                "simulated": bool(df["simulated"].iloc[-1]),
                "volume_unit": str(df["volume_unit"].iloc[-1]),
                "bar_finality": "unknown; daily data may include an unfinished session",
                "freshness_rule": f"calendar_days <= {max_age}; not an exchange calendar"}
    return df.reset_index(drop=True)


def _write_cache(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_klines(symbol_or_raw: str, days: int = 120, end_date=None, adjust: str = "none",
                *, allow_stale: bool = False, refresh: bool = False,
                max_age_days: int | None = None) -> pd.DataFrame:
    """Return daily OHLCV with provenance in columns and freshness in ``df.attrs``.

    ``days`` limits rows, not a guarantee of complete history. Adjustment must be
    supported explicitly by a provider. Stale data raises unless allow_stale=True.
    Cached real data is never used in stub mode (nor are stubs written to cache).
    """
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 10000:
        raise ValueError("days must be an integer from 1 to 10000")
    if adjust not in {"none", "qfq", "hfq"}:
        raise ValueError("adjust must be none, qfq or hfq")
    symbol = normalize(symbol_or_raw)
    end = _as_date(end_date) if end_date is not None else date.today()
    if not isinstance(end, date) or end > date.today():
        raise ValueError("end_date must be a date no later than today")
    cfg = get_config()
    max_age = cfg.max_age_days if max_age_days is None else max_age_days
    if max_age < 0:
        raise ValueError("max_age_days must be nonnegative")
    path = _cache_path(symbol, days, end, adjust)
    cached = None
    if not cfg.use_stubs and path.exists():
        try:
            cached = _decorate(pd.read_parquet(path), cached=True, end_date=end, days=days, max_age=max_age)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached.attrs["fetched_at"])).total_seconds()
            if not refresh and not cached.attrs["stale"] and 0 <= age < cfg.cache_ttl_seconds:
                return cached
        except (OSError, ValueError, KeyError):
            cached = None

    attempts = []
    stale_candidate = None
    for provider_name in _providers():
        try:
            provider = get_provider(provider_name)
            df = provider.fetch_klines(symbol, days, end, adjust=adjust)
            if df is None or df.empty:
                attempts.append(f"{provider_name}:empty")
                continue
            if "adjust" not in df or not df["adjust"].eq(adjust).all():
                raise ValueError("Provider returned a different adjustment convention")
            df = df.copy()
            df["provider"] = provider_name
            df["fetched_at"] = _now()
            df["simulated"] = provider_name == "stub"
            df["volume_unit"] = ("shares" if market(symbol) != "IDX" and
                                 (provider_name in {"yfinance", "futu", "tushare", "stub"} or
                                  (market(symbol) == "CN" and provider_name in {"akshare", "push2"}))
                                 else "source_native")
            df = _decorate(df, cached=False, end_date=end, days=days, max_age=max_age)
            if df.attrs["stale"]:
                if stale_candidate is None or df.attrs["as_of"] > stale_candidate.attrs["as_of"]:
                    stale_candidate = df
                attempts.append(f"{provider_name}:stale")
                continue
            if not cfg.use_stubs:
                _write_cache(path, df)
            return df
        except Exception as exc:
            attempts.append(f"{provider_name}:{type(exc).__name__}")

    candidates = [df for df in (cached, stale_candidate) if df is not None]
    if candidates:
        fallback = max(candidates, key=lambda df: df.attrs["as_of"])
        if allow_stale:
            fallback.attrs["refresh_failed"] = True
            fallback.attrs["attempts"] = attempts
            warnings.warn("Refresh failed; returning explicitly allowed cached/stale data", RuntimeWarning)
            return fallback
        if fallback.attrs["stale"]:
            raise StaleDataError(f"{symbol}: stale data only; as_of={fallback.attrs['as_of']}; {attempts}")
    raise ProviderUnavailableError(f"{symbol}: no usable data; {attempts}")


def load_klines_batch(symbols_raw, days=120, end_date=None, **kwargs):
    return {normalize(s): load_klines(s, days, end_date, **kwargs) for s in symbols_raw}


def _fetch(method, *args, **kwargs):
    attempts = []
    for provider_name in _providers():
        try:
            provider = get_provider(provider_name)
            result = getattr(provider, method)(*args, **kwargs)
            if result is None or (hasattr(result, "__len__") and len(result) == 0):
                attempts.append(f"{provider_name}:empty")
                continue
            meta = {"provider": provider_name, "fetched_at": _now(), "simulated": provider_name == "stub"}
            if isinstance(result, pd.DataFrame):
                result = result.copy()
                result.attrs.update(meta)
            elif isinstance(result, dict):
                result = {**result, **meta}
            elif isinstance(result, list):
                result = [{**row, **meta} for row in result]
            return result
        except Exception as exc:
            attempts.append(f"{provider_name}:{type(exc).__name__}")
    raise ProviderUnavailableError(f"{method}: no usable data; {attempts}")


def snapshot(symbols_raw):
    # Resolve individually: a partial provider batch must not hide missing symbols.
    rows = []
    for symbol in dict.fromkeys(normalize(s) for s in symbols_raw):
        result = _fetch("fetch_snapshot", [symbol])
        matching = [row for row in result if row.get("symbol") == symbol]
        if not matching:
            raise ProviderUnavailableError(f"Missing snapshot for {symbol}")
        for row in matching:
            row.setdefault("as_of", None)
            row["realtime_verified"] = False
        rows.extend(matching)
    return rows


def fundamentals(symbol):
    return _fetch("fetch_fundamentals", normalize(symbol))


def income_statement(symbol):
    return _fetch("fetch_income_statement", normalize(symbol))


def balance_sheet(symbol):
    return _fetch("fetch_balance_sheet", normalize(symbol))


def cash_flow_statement(symbol):
    return _fetch("fetch_cash_flow_statement", normalize(symbol))


def capital_flow(symbol, days=5):
    return _fetch("fetch_capital_flow", normalize(symbol), days)


def plates(symbol):
    return _fetch("fetch_plates", normalize(symbol))


def earnings_calendar(symbol):
    return _fetch("fetch_earnings_calendar", normalize(symbol))


def load_macro(market="US"):
    return _fetch("fetch_macro", market.upper())


def load_commodity():
    return _fetch("fetch_commodity_prices")


def load_northbound_flow(market="CN"):
    return _fetch("fetch_northbound_flow", market.upper())


def name(symbol):
    """Best-effort name from enabled public snapshot providers; no hidden lookup."""
    try:
        row = snapshot([symbol])[0]
        return {"name": row.get("name", ""), "provider": row["provider"]}
    except ProviderUnavailableError:
        return None


def names(symbols_raw):
    return {normalize(s): name(s) for s in symbols_raw}


def run_doctor():
    """Local configuration/dependency check only; does not claim live availability."""
    from .providers.registry import status
    return {"providers": status(), "live_verified": False, "simulated": get_config().use_stubs}


def run_doctor_report():
    return json.dumps(run_doctor(), indent=2, ensure_ascii=False)
