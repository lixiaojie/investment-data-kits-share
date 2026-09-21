"""Futu provider -- Futu OpenD API for HK/CN/US market data."""
from __future__ import annotations

import datetime
import logging
import os
import time

import pandas as pd

from market_data_kit.symbols import normalize, to_futu, market as get_market, exchange
from market_data_kit.providers.base import DataNotFoundError

__all__ = ["FutuProvider"]

logger = logging.getLogger(__name__)

_KLINE_DELAY = 0.5
_FLOW_DELAY = 1.2


def _import_futu():
    try:
        import futu
        return futu
    except ImportError:
        raise ImportError(
            "futu-api not installed. Run: pip install market-data-kit[futu]"
        )


class FutuProvider:
    """Futu OpenD data provider for HK/CN/US markets.

    Requires a running Futu OpenD gateway. Configurable via:
    - MDK_FUTU_HOST (default 127.0.0.1)
    - MDK_FUTU_PORT (default 11111)
    """

    name = "futu"

    def __init__(self, host: str | None = None, port: int | None = None):
        self._host = host or os.getenv("MDK_FUTU_HOST", "127.0.0.1")
        self._port = port or int(os.getenv("MDK_FUTU_PORT", "11111"))
        self._ctx = None

    # ── Connection management ───────────────────────────────────

    def _get_ctx(self):
        if self._ctx is None:
            futu = _import_futu()
            self._ctx = futu.OpenQuoteContext(host=self._host, port=self._port)
        return self._ctx

    def close(self):
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def __del__(self):
        self.close()

    # ── Klines ──────────────────────────────────────────────────

    def fetch_klines(
        self,
        symbol: str,
        days: int,
        end_date: datetime.date | None = None,
        adjust: str = "none",
    ) -> pd.DataFrame:
        futu = _import_futu()
        ctx = self._get_ctx()
        futu_code = to_futu(symbol)

        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))

        # Split into yearly chunks to avoid Futu API hanging on large ranges
        all_rows: list[pd.DataFrame] = []
        chunk_start = start_date
        while chunk_start < end_date:
            chunk_end = min(chunk_start + datetime.timedelta(days=365), end_date)
            page_req_key = None

            while True:
                ret, data, page_req_key = ctx.request_history_kline(
                    futu_code,
                    start=chunk_start.strftime("%Y-%m-%d"),
                    end=chunk_end.strftime("%Y-%m-%d"),
                    ktype=futu.KLType.K_DAY,
                    autype={"none": futu.AuType.NONE, "qfq": futu.AuType.QFQ, "hfq": futu.AuType.HFQ}[adjust],
                    max_count=1000,
                    page_req_key=page_req_key,
                )
                if ret != futu.RET_OK:
                    logger.warning("Futu kline chunk failed for %s (%s~%s): %s",
                                   symbol, chunk_start, chunk_end, data)
                    break
                if data is not None and not data.empty:
                    all_rows.append(data)
                if page_req_key is None:
                    break
                time.sleep(_KLINE_DELAY)

            chunk_start = chunk_end + datetime.timedelta(days=1)
            time.sleep(_KLINE_DELAY)

        if not all_rows:
            raise DataNotFoundError(f"No kline data from Futu for {symbol}")

        raw = pd.concat(all_rows, ignore_index=True)
        result = self._map_kline_columns(raw, symbol)
        result["adjust"] = adjust
        return result

    @staticmethod
    def _map_kline_columns(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        exch = exchange(symbol)
        n = len(raw)
        result = pd.DataFrame()
        result["symbol"] = [symbol] * n
        result["exchange"] = [exch] * n
        result["date"] = pd.to_datetime(raw["time_key"]).dt.date
        result["open"] = raw["open"].astype(float).values
        result["high"] = raw["high"].astype(float).values
        result["low"] = raw["low"].astype(float).values
        result["close"] = raw["close"].astype(float).values
        result["volume"] = raw["volume"].astype(int).values
        result["turnover"] = (
            raw["turnover"].astype(float).values
            if "turnover" in raw.columns
            else [float("nan")] * n
        )
        result["pct_change"] = (
            raw["change_rate"].astype(float).values
            if "change_rate" in raw.columns
            else [float("nan")] * n
        )
        result["prev_close"] = (
            raw["last_close"].astype(float).values
            if "last_close" in raw.columns
            else [float("nan")] * n
        )
        result["turnover_rate"] = (
            raw["turnover_rate"].astype(float).values
            if "turnover_rate" in raw.columns
            else [float("nan")] * n
        )
        result["pe_ratio"] = (
            raw["pe_ratio"].astype(float).values
            if "pe_ratio" in raw.columns
            else [float("nan")] * n
        )
        result["adjust"] = ["none"] * n
        return result.sort_values("date").reset_index(drop=True)

    # ── Snapshot ────────────────────────────────────────────────

    def fetch_snapshot(self, symbols: list[str]) -> list[dict]:
        futu = _import_futu()
        ctx = self._get_ctx()
        futu_codes = [to_futu(s) for s in symbols]

        ret, data = ctx.get_market_snapshot(futu_codes)
        if ret != futu.RET_OK or data is None or data.empty:
            return []

        results = []
        for _, row in data.iterrows():
            sym = normalize(row["code"])
            results.append({
                "symbol": sym,
                "name": row.get("name", ""),
                "last_price": float(row.get("last_price", 0)),
                "pct_change": float(row.get("price_change_rate", 0)),
                "volume": int(row.get("volume", 0)),
                "turnover": float(row.get("turnover", 0)),
                "high": float(row.get("high_price", 0)),
                "low": float(row.get("low_price", 0)),
                "open": float(row.get("open_price", 0)),
                "prev_close": float(row.get("prev_close_price", 0)),
                "pe_ratio": float(row.get("pe_ratio", 0)),
                "market_cap": float(row.get("market_val", 0)),
            })
        return results

    # ── Capital flow ────────────────────────────────────────────

    def fetch_capital_flow(self, symbol: str, days: int = 5) -> pd.DataFrame:
        """Fetch per-stock capital flow via Futu OpenD.

        Supports HK, CN, US markets. Returns DataFrame with columns:
        symbol, date, main_in, super_in, big_in, mid_in, small_in, in_flow.
        Values are in HKD/CNY/USD per market.
        """
        futu = _import_futu()
        ctx = self._get_ctx()
        futu_code = to_futu(symbol)

        ret, data = ctx.get_capital_flow(futu_code, period_type="DAY")
        if ret != futu.RET_OK or data is None or data.empty:
            raise DataNotFoundError(
                f"Futu get_capital_flow failed for {symbol}: {data}"
            )

        rows = []
        for _, row in data.iterrows():
            rows.append({
                "symbol": symbol,
                "date": pd.to_datetime(row["capital_flow_item_time"]).date(),
                "main_in": float(row.get("main_in_flow", 0) or 0),
                "super_in": float(row.get("super_in_flow", 0) or 0),
                "big_in": float(row.get("big_in_flow", 0) or 0),
                "mid_in": float(row.get("mid_in_flow", 0) or 0),
                "small_in": float(row.get("sml_in_flow", 0) or 0),
                "in_flow": float(row.get("in_flow", 0) or 0),
            })

        result = pd.DataFrame(rows)
        if result.empty:
            raise DataNotFoundError(f"No capital flow rows for {symbol}")

        result = result.sort_values("date").reset_index(drop=True)
        if days > 0:
            result = result.tail(days).reset_index(drop=True)

        time.sleep(_FLOW_DELAY)
        return result

    # ── Fundamentals (from snapshot) ────────────────────────────

    def fetch_fundamentals(self, symbol: str) -> dict:
        snaps = self.fetch_snapshot([symbol])
        if not snaps:
            raise DataNotFoundError(f"No Futu snapshot for {symbol}")
        snap = snaps[0]
        return {
            "symbol": symbol,
            "pe_ratio": snap.get("pe_ratio"),
            "market_cap": snap.get("market_cap"),
        }

    # ── Plates ─────────────────────────────────────────────────

    def fetch_plates(self, symbol: str) -> list[dict]:
        """Fetch plate memberships for a symbol via Futu OpenD.

        Returns list of plate metadata (no symbols list — call
        fetch_plate_stocks(plate_code) when members are needed).

        Each entry: {symbol, name, code, type, plate_type}
        - type: "industry" / "concept" / "other" (mapped from Futu plate_type)
        - code: plate_code, can be passed to fetch_plate_stocks
        """
        ctx = self._get_ctx()
        futu_code = to_futu(symbol)
        ret, df = ctx.get_owner_plate([futu_code])
        if ret != 0 or df is None or len(df) == 0:
            raise DataNotFoundError(f"No plates for {symbol} (Futu ret={ret})")

        type_map = {"INDUSTRY": "industry", "CONCEPT": "concept", "OTHER": "other"}
        plates = []
        for _, row in df.iterrows():
            ftype = str(row.get("plate_type", "")).upper()
            plates.append({
                "symbol": symbol,
                "name": str(row.get("plate_name", "")),
                "code": str(row.get("plate_code", "")),
                "type": type_map.get(ftype, ftype.lower() or "other"),
                "plate_type": ftype,  # original Futu value for debugging
            })
        return plates

    def fetch_plate_stocks(self, plate_code: str) -> list[dict]:
        """Fetch member stocks of a plate.

        Args:
            plate_code: e.g. "HK.LIST23586" or "SH.LIST23335" — get from
                fetch_plates result["code"].

        Returns list of {symbol, name} dicts (symbol normalized to MDK format).
        """
        ctx = self._get_ctx()
        ret, df = ctx.get_plate_stock(plate_code)
        if ret != 0 or df is None or len(df) == 0:
            raise DataNotFoundError(
                f"No member stocks for plate {plate_code} (Futu ret={ret})"
            )

        members = []
        for _, row in df.iterrows():
            futu_sym = str(row.get("code", ""))
            if not futu_sym:
                continue
            try:
                norm_sym = normalize(futu_sym)
            except Exception:
                norm_sym = futu_sym  # fall back to raw if normalize fails
            members.append({
                "symbol": norm_sym,
                "name": str(row.get("stock_name", "")),
            })
        return members

    # ── Healthcheck ─────────────────────────────────────────────

    def healthcheck(self) -> bool:
        try:
            ctx = self._get_ctx()
            return ctx is not None
        except Exception:
            return False
