"""Stub provider — generates realistic fake data for development."""
from __future__ import annotations

import datetime
import hashlib
import random

import numpy as np
import pandas as pd

__all__ = ["StubProvider"]


class StubProvider:
    """Returns structurally valid fake data, seeded by symbol hash for reproducibility."""

    name = "stub"

    def _seed(self, symbol: str) -> int:
        return int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)

    def fetch_klines(
        self,
        symbol: str,
        days: int,
        end_date: datetime.date | None = None,
        adjust: str = "none",
    ) -> pd.DataFrame:
        seed = self._seed(symbol)
        rng = np.random.RandomState(seed)

        if end_date is None:
            end_date = datetime.date.today()

        from market_data_kit.symbols import exchange, market as get_market

        mkt = get_market(symbol)
        exch = exchange(symbol)

        # Market-appropriate base price
        base_price = {"HK": 50 + rng.random() * 400,
                      "CN": 10 + rng.random() * 150,
                      "US": 20 + rng.random() * 800}.get(mkt, 100)

        dates = [end_date - datetime.timedelta(days=i) for i in range(days)]
        dates = sorted(dates)

        # Random walk for close prices
        returns = rng.normal(0, 0.02, len(dates))
        close = base_price * np.cumprod(1 + returns)

        rows = []
        for i, d in enumerate(dates):
            c = close[i]
            daily_range = c * rng.uniform(0.005, 0.03)
            rows.append({
                "symbol": symbol,
                "exchange": exch,
                "date": d,
                "open": round(c + rng.normal(0, daily_range * 0.3), 2),
                "high": round(c + abs(rng.normal(0, daily_range)), 2),
                "low": round(c - abs(rng.normal(0, daily_range)), 2),
                "close": round(c, 2),
                "volume": int(rng.randint(100000, 50000000)),
                "turnover": round(c * rng.randint(100000, 50000000), 2),
                "pct_change": round(returns[i] * 100, 2),
                "prev_close": round(close[i - 1] if i > 0 else c, 2),
                "turnover_rate": round(rng.uniform(0.01, 2.0), 4),
                "pe_ratio": round(rng.uniform(5, 60), 2),
                "adjust": adjust,
            })
        return pd.DataFrame(rows)

    def fetch_snapshot(self, symbols: list[str]) -> list[dict]:
        results = []
        for sym in symbols:
            seed = self._seed(sym)
            rng = random.Random(seed)
            from market_data_kit.symbols import market as get_market

            mkt = get_market(sym)
            base = {"HK": 200, "CN": 50, "US": 300}.get(mkt, 100)
            price = round(base * (0.5 + rng.random()), 2)
            results.append({
                "symbol": sym,
                "name": f"Stub_{sym}",
                "last_price": price,
                "pct_change": round(rng.uniform(-5, 5), 2),
                "volume": rng.randint(100000, 50000000),
                "turnover": round(price * rng.randint(100000, 10000000), 2),
                "high": round(price * 1.02, 2),
                "low": round(price * 0.98, 2),
                "open": round(price * (0.99 + rng.random() * 0.02), 2),
                "prev_close": round(price * (0.99 + rng.random() * 0.02), 2),
                "pe_ratio": round(rng.uniform(8, 50), 1),
                "pb_ratio": round(rng.uniform(0.5, 10), 2),
                "market_cap": round(price * rng.randint(1000000, 1000000000), 0),
            })
        return results

    def fetch_fundamentals(self, symbol: str) -> dict:
        seed = self._seed(symbol)
        rng = random.Random(seed)
        return {
            "symbol": symbol,
            "pe_ratio": round(rng.uniform(5, 60), 2),
            "pb_ratio": round(rng.uniform(0.3, 15), 2),
            "market_cap": round(rng.uniform(1e9, 1e12), 0),
            "roe": round(rng.uniform(-0.1, 0.4), 4),
            "eps": round(rng.uniform(0.1, 20), 2),
            "dividend_yield": round(rng.uniform(0, 0.06), 4),
        }

    def fetch_capital_flow(self, symbol: str, days: int = 5) -> pd.DataFrame:
        seed = self._seed(symbol)
        rng = np.random.RandomState(seed)
        end = datetime.date.today()
        rows = []
        for i in range(days):
            d = end - datetime.timedelta(days=i)
            rows.append({
                "symbol": symbol,
                "date": d,
                "super_in": round(float(rng.normal(0, 1e8)), 2),
                "big_in": round(float(rng.normal(0, 5e7)), 2),
                "mid_in": round(float(rng.normal(0, 2e7)), 2),
                "small_in": round(float(rng.normal(0, 1e7)), 2),
                "main_in": round(float(rng.normal(0, 1.5e8)), 2),
            })
        return pd.DataFrame(rows)

    def fetch_plates(self, symbol: str) -> list[dict]:
        seed = self._seed(symbol)
        rng = random.Random(seed)
        plates = ["银行", "科技", "消费", "医药", "新能源", "半导体", "白酒", "地产"]
        n = rng.randint(1, 3)
        return [
            {"symbol": symbol, "type": "industry", "name": rng.choice(plates)}
            for _ in range(n)
        ]

    def fetch_balance_sheet(self, symbol: str) -> list[dict]:
        seed = self._seed(symbol)
        rng = random.Random(seed)
        records = []
        for q in range(4):
            year = 2025
            period = f"{year}Q{q + 1}"
            ta = round(rng.uniform(1e9, 1e12), 0)
            records.append({
                "symbol": symbol,
                "period": period,
                "total_assets": ta,
                "total_liabilities": round(ta * rng.uniform(0.3, 0.7), 0),
                "equity": round(ta * rng.uniform(0.3, 0.7), 0),
                "current_assets": round(ta * rng.uniform(0.2, 0.5), 0),
                "current_liabilities": round(ta * rng.uniform(0.1, 0.3), 0),
                "cash": round(ta * rng.uniform(0.05, 0.2), 0),
                "inventory": round(ta * rng.uniform(0.01, 0.1), 0),
                "receivables": round(ta * rng.uniform(0.02, 0.15), 0),
            })
        return records

    def fetch_income_statement(self, symbol: str) -> list[dict]:
        seed = self._seed(symbol)
        rng = random.Random(seed)
        records = []
        for q in range(4):
            year = 2025
            period = f"{year}Q{q + 1}"
            revenue = round(rng.uniform(1e8, 1e11), 0)
            records.append({
                "symbol": symbol,
                "period": period,
                "revenue": revenue,
                "cost_of_revenue": round(revenue * rng.uniform(0.4, 0.7), 0),
                "gross_profit": round(revenue * rng.uniform(0.3, 0.6), 0),
                "operating_income": round(revenue * rng.uniform(0.1, 0.3), 0),
                "net_income": round(revenue * rng.uniform(0.05, 0.2), 0),
            })
        return records

    def fetch_cash_flow_statement(self, symbol: str) -> list[dict]:
        seed = self._seed(symbol)
        rng = random.Random(seed)
        records = []
        for q in range(4):
            year = 2025
            period = f"{year}Q{q + 1}"
            operating = round(rng.uniform(1e7, 1e10), 0)
            records.append({
                "symbol": symbol,
                "period": period,
                "operating_cf": operating,
                "investing_cf": round(-operating * rng.uniform(0.3, 0.8), 0),
                "financing_cf": round(-operating * rng.uniform(0.1, 0.5), 0),
                "net_cf": round(operating * rng.uniform(-0.2, 0.5), 0),
            })
        return records

    def fetch_macro(self, market: str = "US") -> list[dict]:
        """Return stub macro data."""
        today = datetime.date.today()
        indicators = {
            "US": [
                ("fed_funds_rate", 5.25, "%"),
                ("treasury_10y", 4.35, "%"),
                ("cpi_yoy", 3.1, "%"),
            ],
            "CN": [
                ("lpr_1y", 3.45, "%"),
                ("lpr_5y", 3.95, "%"),
                ("pmi_manufacturing", 50.2, ""),
                ("cn_cpi_yoy", 0.7, "%"),
            ],
            "HK": [
                ("hk_base_rate", 5.75, "%"),
            ],
        }
        data = indicators.get(market.upper(), [])
        return [
            {
                "indicator": name,
                "date": today,
                "value": value,
                "unit": unit,
                "source": "stub",
            }
            for name, value, unit in data
        ]

    def fetch_commodity_prices(self, symbols=None) -> list[dict]:
        """Return stub commodity prices."""
        today = datetime.date.today()
        return [
            {"symbol": "GC=F", "date": today, "price": 2350.0, "pct_change": 0.5, "unit": "USD/oz", "source": "stub"},
            {"symbol": "CL=F", "date": today, "price": 78.5, "pct_change": -1.2, "unit": "USD/bbl", "source": "stub"},
            {"symbol": "SI=F", "date": today, "price": 27.8, "pct_change": 0.3, "unit": "USD/oz", "source": "stub"},
        ]

    def healthcheck(self) -> bool:
        return True
