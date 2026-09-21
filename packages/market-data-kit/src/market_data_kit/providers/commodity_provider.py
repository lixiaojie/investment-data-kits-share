"""CommodityProvider — commodity prices via yfinance."""

from __future__ import annotations

import datetime
import logging

from market_data_kit.providers.base import DataNotFoundError

__all__ = ["CommodityProvider"]

logger = logging.getLogger(__name__)

COMMODITY_SYMBOLS = {
    "GC=F": {"name": "黄金", "unit": "USD/oz"},
    "SI=F": {"name": "白银", "unit": "USD/oz"},
    "CL=F": {"name": "WTI原油", "unit": "USD/bbl"},
    "BZ=F": {"name": "布伦特原油", "unit": "USD/bbl"},
    "NG=F": {"name": "天然气", "unit": "USD/MMBtu"},
    "HG=F": {"name": "铜", "unit": "USD/lb"},
}


def _import_yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install market-data-kit[yfinance]")


class CommodityProvider:
    name = "commodity"

    def fetch_commodity_prices(self, symbols: dict[str, dict] | None = None) -> list[dict]:
        """Fetch current commodity prices via yfinance.

        Args:
            symbols: Optional {yf_symbol: {name, unit}} dict. Defaults to COMMODITY_SYMBOLS.

        Returns:
            List of dicts matching CommodityStore schema.
        """
        yf = _import_yf()
        if symbols is None:
            symbols = COMMODITY_SYMBOLS

        results = []

        for yf_sym, info in symbols.items():
            try:
                ticker = yf.Ticker(yf_sym)
                fast_info = ticker.fast_info
                price = getattr(fast_info, "last_price", None)
                prev_close = getattr(fast_info, "previous_close", None)

                if price is None:
                    # Fallback to info dict
                    info_dict = ticker.info or {}
                    price = info_dict.get("regularMarketPrice") or info_dict.get("currentPrice")
                    prev_close = info_dict.get("regularMarketPreviousClose") or info_dict.get("previousClose")

                if price is None:
                    logger.warning("No price for %s", yf_sym)
                    continue

                pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

                results.append({
                    "symbol": yf_sym,
                    "date": None,  # fast_info exposes no verified observation timestamp
                    "as_of": None,
                    "price": float(price),
                    "pct_change": round(pct, 2),
                    "unit": info.get("unit", "USD"),
                    "source": "yfinance",
                })
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", yf_sym, e)
                continue

        if not results:
            raise DataNotFoundError("No commodity prices fetched")

        return results

    def healthcheck(self) -> bool:
        try:
            _import_yf()
            return True
        except ImportError:
            return False
