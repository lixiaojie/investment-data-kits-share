"""Tushare provider — A-share historical klines via Tushare Pro API."""
from __future__ import annotations

import datetime
import logging
import os
import time

import pandas as pd

from market_data_kit.symbols import to_tushare, market as get_market, exchange
from market_data_kit.providers.base import DataNotFoundError

__all__ = ["TushareProvider"]

logger = logging.getLogger(__name__)

_CALL_INTERVAL = 0.3


def _import_tushare():
    try:
        import tushare as ts
        return ts
    except ImportError:
        raise ImportError("tushare not installed. Run: pip install market-data-kit[tushare]")


class TushareProvider:
    name = "tushare"

    def __init__(self, token: str | None = None):
        self._token = token or os.getenv("MDK_TUSHARE_TOKEN", "")
        self._pro = None
        self._last_call = 0.0

    def _get_pro(self):
        if self._pro is None:
            ts = _import_tushare()
            if not self._token:
                raise DataNotFoundError("MDK_TUSHARE_TOKEN not set")
            self._pro = ts.pro_api(self._token)
        return self._pro

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < _CALL_INTERVAL:
            time.sleep(_CALL_INTERVAL - elapsed)
        self._last_call = time.time()

    def fetch_klines(self, symbol: str, days: int,
                     end_date: datetime.date | None = None, adjust: str = "none") -> pd.DataFrame:
        if adjust != "none":
            raise NotImplementedError("Tushare daily adapter supports only none")
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"Tushare only supports CN market, got {mkt}")

        pro = self._get_pro()
        ts_code = to_tushare(symbol)

        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))

        self._throttle()
        df = pro.daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )

        if df is None or df.empty:
            raise DataNotFoundError(f"No Tushare data for {symbol}")

        return self._map_columns(df, symbol)

    def _map_columns(self, df, symbol):
        exch = exchange(symbol)
        n = len(df)
        result = pd.DataFrame({
            "symbol": [symbol] * n,
            "exchange": [exch] * n,
            "date": pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date.values,
            "open": df["open"].astype(float).values,
            "high": df["high"].astype(float).values,
            "low": df["low"].astype(float).values,
            "close": df["close"].astype(float).values,
            "volume": (df["vol"].astype(float) * 100).round().astype("int64").values,
            "turnover": df["amount"].astype(float).values * 1000 if "amount" in df.columns else [float("nan")] * n,
            "pct_change": df["pct_chg"].astype(float).values if "pct_chg" in df.columns else [float("nan")] * n,
            "prev_close": df["pre_close"].astype(float).values if "pre_close" in df.columns else [float("nan")] * n,
            "turnover_rate": [float("nan")] * n,
            "pe_ratio": [float("nan")] * n,
            "adjust": ["none"] * n,
        })
        return result.sort_values("date").reset_index(drop=True)

    def fetch_snapshot(self, symbols):
        raise NotImplementedError("Tushare does not support real-time snapshots")

    def fetch_fundamentals(self, symbol):
        raise NotImplementedError("Tushare fundamentals not in Phase 2 scope")

    def fetch_capital_flow(self, symbol, days=5):
        raise NotImplementedError("Tushare capital_flow not in Phase 2 scope")

    def fetch_plates(self, symbol):
        raise NotImplementedError("Tushare plates not in Phase 2 scope")

    def healthcheck(self) -> bool:
        try:
            _import_tushare()
            return bool(self._token)
        except ImportError:
            return False
