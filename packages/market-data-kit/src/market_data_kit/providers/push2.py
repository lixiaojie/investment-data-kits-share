"""Push2 provider -- eastmoney HTTP API for CN/US snapshots and CN klines.

Uses the caller's configured proxy settings. Access and rate limits are controlled
by the upstream service; a connection failure does not identify its cause.
"""
from __future__ import annotations

import datetime
import json
import logging
import random
import time
import urllib.request
from typing import Any

import pandas as pd

from market_data_kit.symbols import normalize, market as get_market, exchange, to_push2_secid
from market_data_kit.providers.proxy_cleanup import clear_proxy

__all__ = ["Push2Provider"]

logger = logging.getLogger(__name__)

_SNAP_URL = "http://push2.eastmoney.com/api/qt/ulist.np/get"
_SNAP_FIELDS = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23"
_HIST_URL = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
_FLOW_URL = "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"


class Push2Provider:
    """Eastmoney push2 HTTP API -- CN/US snapshots, CN daily klines."""

    name = "push2"

    def fetch_snapshot(self, symbols: list[str]) -> list[dict]:
        """Batch snapshot for CN/US symbols. HK symbols are silently skipped."""
        secids: list[str] = []
        sym_map: dict[str, str] = {}
        for sym in symbols:
            mkt = get_market(sym)
            if mkt == "HK":
                continue  # push2 doesn't support HK
            try:
                secid = to_push2_secid(sym)
                secids.append(secid)
                sym_map[secid.split(".")[-1]] = sym  # code -> symbol mapping
            except Exception:
                continue

        if not secids:
            return []

        params = f"fltt=2&fields={_SNAP_FIELDS}&secids={','.join(secids)}"
        url = f"{_SNAP_URL}?{params}"

        with clear_proxy():
            data = _fetch_json(url)

        if not data or "data" not in data or "diff" not in data["data"]:
            return []

        results: list[dict] = []
        for item in data["data"]["diff"]:
            code = str(item.get("f12", ""))
            sym = sym_map.get(code)
            if not sym:
                # Try to reconstruct symbol from secid market id
                f13 = item.get("f13", 0)
                if f13 == 1:
                    sym = normalize(f"SH.{code}")
                elif f13 == 0:
                    sym = normalize(f"SZ.{code}")
                else:
                    sym = normalize(code) if code.isalpha() else f"CN.{code}"

            results.append({
                "symbol": sym,
                "name": item.get("f14", ""),
                "last_price": _safe_float(item.get("f2")),
                "pct_change": _safe_float(item.get("f3")),
                "volume": _safe_int(item.get("f5")),
                "turnover": _safe_float(item.get("f6")),
                "high": _safe_float(item.get("f15")),
                "low": _safe_float(item.get("f16")),
                "open": _safe_float(item.get("f17")),
                "prev_close": _safe_float(item.get("f18")),
                "turnover_rate": _safe_float(item.get("f8")),
                "pe_ratio": _safe_float(item.get("f9")),
                "pb_ratio": _safe_float(item.get("f23")),
                "market_cap": _safe_float(item.get("f20")),
                "circ_market_cap": _safe_float(item.get("f21")),
            })

        return results

    def fetch_klines(self, symbol: str, days: int,
                     end_date: datetime.date | None = None, adjust: str = "none") -> pd.DataFrame:
        """Daily klines with explicit adjustment for CN symbols only."""
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError("push2 klines only supports CN market")

        secid = to_push2_secid(symbol)
        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))  # padding for non-trading days

        params = (
            f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt={dict(none=0, qfq=1, hfq=2)[adjust]}"
            f"&beg={start_date.strftime('%Y%m%d')}&end={end_date.strftime('%Y%m%d')}"
        )
        url = f"{_HIST_URL}?{params}"

        with clear_proxy():
            data = _fetch_json(url)

        if not data or "data" not in data or not data["data"] or "klines" not in data["data"]:
            return pd.DataFrame()

        rows: list[dict] = []
        exch = exchange(symbol)
        for line in data["data"]["klines"]:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            rows.append({
                "symbol": symbol,
                "exchange": exch,
                "date": datetime.date.fromisoformat(parts[0]),
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": round(float(parts[5]) * 100),  # CN source lots -> shares
                "turnover": float(parts[6]),
                "pct_change": float(parts[8]) if parts[8] != "-" else 0.0,
                "prev_close": 0.0,  # calculated below
                "turnover_rate": float(parts[10]) if parts[10] != "-" else 0.0,
                "pe_ratio": float("nan"),
                "adjust": adjust,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Calculate prev_close from close and pct_change
        mask = df["pct_change"] != 0
        df.loc[mask, "prev_close"] = df.loc[mask, "close"] / (1 + df.loc[mask, "pct_change"] / 100)
        # Filter to requested range
        cutoff = start_date
        df = df[(df["date"] >= cutoff) & (df["date"] <= end_date)]
        return df.sort_values("date").tail(days).reset_index(drop=True)

    def fetch_fundamentals(self, symbol: str) -> dict:
        """Fetch basic fundamentals from snapshot data."""
        snaps = self.fetch_snapshot([symbol])
        if not snaps:
            raise NotImplementedError("No snapshot data available for fundamentals")
        snap = snaps[0]
        return {
            "symbol": symbol,
            "pe_ratio": snap.get("pe_ratio"),
            "pb_ratio": snap.get("pb_ratio"),
            "market_cap": snap.get("market_cap"),
            "circ_market_cap": snap.get("circ_market_cap"),
        }

    def fetch_capital_flow(self, symbol: str, days: int = 5) -> pd.DataFrame:
        """Fetch capital flow via eastmoney HTTP API. CN and HK."""
        mkt = get_market(symbol)
        if mkt not in ("CN", "HK"):
            raise NotImplementedError(f"push2 capital_flow only for CN/HK, got {mkt}")

        secid = to_push2_secid(symbol)
        lmt = max(days, 30)  # fetch at least 30 days
        params = (
            f"lmt={lmt}&klt=101&secid={secid}"
            f"&fields1=f1,f2,f3,f7"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
        )
        url = f"{_FLOW_URL}?{params}"

        with clear_proxy():
            data = _fetch_json(url)

        if not data or "data" not in data or not data["data"] or "klines" not in data["data"]:
            return pd.DataFrame()

        rows: list[dict] = []
        for line in data["data"]["klines"]:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            # Format: date, main_in, super_in, big_in, mid_in, small_in, ...
            rows.append({
                "symbol": symbol,
                "date": datetime.date.fromisoformat(parts[0]),
                "main_in": _safe_float(parts[1]),
                "super_in": _safe_float(parts[2]),
                "big_in": _safe_float(parts[3]),
                "mid_in": _safe_float(parts[4]),
                "small_in": _safe_float(parts[5]),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if days > 0:
            df = df.sort_values("date").tail(days)
        return df.reset_index(drop=True)

    def fetch_plates(self, symbol: str) -> list[dict]:
        raise NotImplementedError("push2 plates not implemented")

    def healthcheck(self) -> bool:
        try:
            with clear_proxy():
                data = _fetch_json(f"{_SNAP_URL}?fltt=2&fields=f2&secids=1.000001")
            return data is not None and "data" in data
        except Exception:
            return False


# ── Helpers ────────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/17.4",
]


def _fetch_json(url: str, timeout: int = 10, retries: int = 1) -> dict | None:
    """HTTP GET and parse JSON.

    Preserves the caller's configured proxy settings.
    Rotates User-Agent to reduce fingerprinting.
    retries=1 (default) means no retry at this level — caller handles retry logic.
    """
    opener = urllib.request.build_opener()
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", random.choice(_USER_AGENTS))
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    logger.warning("push2 HTTP error: %s", last_err)
    raise last_err


def _safe_float(val: Any) -> float:
    if val is None or val == "-":
        return float("nan")
    try:
        return float(val)
    except (ValueError, TypeError):
        return float("nan")


def _safe_int(val: Any) -> int:
    if val is None or val == "-":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0
