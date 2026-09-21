"""yfinance provider — Yahoo Finance for US/HK/CN market data."""
from __future__ import annotations

import datetime
import logging
import math

import pandas as pd

from market_data_kit.symbols import to_yfinance, market as get_market, exchange, normalize
from market_data_kit.providers.base import DataNotFoundError, ProviderRateLimitError

__all__ = ["YfinanceProvider"]

logger = logging.getLogger(__name__)


def _import_yfinance():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install market-data-kit[yfinance]")


class YfinanceProvider:
    name = "yfinance"

    def fetch_klines(self, symbol: str, days: int,
                     end_date: datetime.date | None = None, adjust: str = "none") -> pd.DataFrame:
        if adjust != "none":
            raise NotImplementedError("Yahoo price adjustment is not interchangeable with qfq/hfq")
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)

        if end_date is None:
            end_date = datetime.date.today()
        # yfinance 'end' is exclusive, add 1 day
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))
        end_plus = end_date + datetime.timedelta(days=1)

        ticker = yf.Ticker(yf_sym)
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_plus.strftime("%Y-%m-%d"),
            auto_adjust=False,
        )

        if df is None or df.empty:
            raise DataNotFoundError(f"No yfinance data for {symbol} ({yf_sym})")

        return self._map_columns(df, symbol)

    def _map_columns(self, df, symbol):
        exch = exchange(symbol)
        df = df.reset_index()
        n = len(df)

        # yfinance columns: Date, Open, High, Low, Close, Adj Close, Volume
        result = pd.DataFrame({
            "symbol": [symbol] * n,
            "exchange": [exch] * n,
            "date": pd.to_datetime(df["Date"]).dt.date.values,
            "open": df["Open"].astype(float).values,
            "high": df["High"].astype(float).values,
            "low": df["Low"].astype(float).values,
            "close": df["Close"].astype(float).values,
            "volume": df["Volume"].astype(int).values,
            "turnover": [float("nan")] * n,
            "pct_change": [float("nan")] * n,
            "prev_close": [float("nan")] * n,
            "turnover_rate": [float("nan")] * n,
            "pe_ratio": [float("nan")] * n,
            "adjust": ["none"] * n,
        })

        # Calculate pct_change and prev_close
        result["prev_close"] = result["close"].shift(1)
        result["pct_change"] = result["close"].pct_change() * 100

        # Filter NaN prices (yfinance sometimes returns NaN for delisted/invalid tickers)
        result = result.dropna(subset=["close"])

        return result.sort_values("date").reset_index(drop=True)

    def fetch_snapshot(self, symbols: list[str]) -> list[dict]:
        yf = _import_yfinance()
        results = []
        for symbol in symbols:
            yf_sym = to_yfinance(symbol)
            try:
                ticker = yf.Ticker(yf_sym)
                info = ticker.info or {}
                price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                if not price or (isinstance(price, float) and math.isnan(price)):
                    continue
                results.append({
                    "symbol": symbol,
                    "name": info.get("shortName", ""),
                    "last_price": float(price),
                    "pct_change": float(info.get("regularMarketChangePercent", 0)),
                    "volume": int(info.get("regularMarketVolume", 0)),
                    "turnover": float("nan"),
                    "high": float(info.get("dayHigh", 0)),
                    "low": float(info.get("dayLow", 0)),
                    "open": float(info.get("regularMarketOpen", 0)),
                    "prev_close": float(info.get("regularMarketPreviousClose", 0)),
                    "pe_ratio": float(info.get("trailingPE", 0)) if info.get("trailingPE") else float("nan"),
                    "pb_ratio": float(info.get("priceToBook", 0)) if info.get("priceToBook") else float("nan"),
                    "market_cap": float(info.get("marketCap", 0)),
                })
            except Exception as e:
                logger.warning("yfinance snapshot error for %s: %s", symbol, e)
                continue
        return results

    def fetch_fundamentals(self, symbol: str) -> dict:
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)
        info = ticker.info or {}

        if not info or not info.get("currentPrice"):
            raise DataNotFoundError(f"No yfinance info for {symbol}")

        return {
            "symbol": symbol,
            "pe_ratio": _safe_float(info.get("trailingPE")),
            "pb_ratio": _safe_float(info.get("priceToBook")),
            "market_cap": _safe_float(info.get("marketCap")),
            "roe": _safe_float(info.get("returnOnEquity")),
            "dividend_yield": _safe_float(info.get("dividendYield")),
            "revenue": _safe_float(info.get("totalRevenue")),
            "net_profit": _safe_float(info.get("netIncomeToCommon")),
            "eps": _safe_float(info.get("trailingEps")),
        }

    def fetch_capital_flow(self, symbol, days=5):
        raise NotImplementedError("yfinance does not support capital flow")

    def fetch_plates(self, symbol):
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)
        info = ticker.info or {}

        plates = []
        if info.get("sector"):
            plates.append({"symbol": symbol, "type": "industry", "name": info["sector"]})
        if info.get("industry"):
            plates.append({"symbol": symbol, "type": "concept", "name": info["industry"]})

        if not plates:
            raise DataNotFoundError(f"No plate info for {symbol}")
        return plates

    def fetch_balance_sheet(self, symbol: str) -> list[dict]:
        """Fetch quarterly balance sheet via yfinance (HK/US/CN)."""
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)

        # quarterly_balance_sheet: columns are dates, rows are line items
        bs = ticker.quarterly_balance_sheet
        if bs is None or bs.empty:
            bs = ticker.balance_sheet
        if bs is None or bs.empty:
            raise DataNotFoundError(f"No balance sheet for {symbol}")

        records = []
        for col_date in bs.columns:
            dt = pd.to_datetime(col_date)
            quarter = (dt.month - 1) // 3 + 1
            period_label = f"{dt.year}Q{quarter}"

            col = bs[col_date]
            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "point_in_time",
                "period_end": dt.date().isoformat(),
                "total_assets": _safe_float(col.get("Total Assets")),
                "total_liabilities": _safe_float(col.get("Total Liabilities Net Minority Interest") or col.get("Total Liab")),
                "equity": _safe_float(col.get("Stockholders Equity") or col.get("Total Stockholders Equity")),
                "current_assets": _safe_float(col.get("Current Assets")),
                "current_liabilities": _safe_float(col.get("Current Liabilities")),
                "cash": _safe_float(col.get("Cash And Cash Equivalents") or col.get("Cash")),
                "inventory": _safe_float(col.get("Inventory")),
                "receivables": _safe_float(col.get("Accounts Receivable") or col.get("Net Receivables")),
            })
        return records

    def fetch_income_statement(self, symbol: str) -> list[dict]:
        """Fetch income statement from yfinance (HK/US/CN)."""
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)
        df = ticker.income_stmt

        if df is None or df.empty:
            raise DataNotFoundError(f"No income statement for {symbol}")

        records = []
        for col_date in df.columns:
            dt = pd.to_datetime(col_date)
            month = dt.month
            quarter = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, f"M{month:02d}")
            period_label = f"{dt.year}{quarter}"

            col = df[col_date]
            revenue = _safe_float(col.get("Total Revenue"))
            cost = _safe_float(col.get("Cost Of Revenue"))
            gross = _safe_float(col.get("Gross Profit"))
            op_income = _safe_float(col.get("Operating Income"))
            net_income = _safe_float(col.get("Net Income"))

            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "annual",
                "period_end": dt.date().isoformat(),
                "revenue": revenue,
                "cost_of_revenue": cost,
                "gross_profit": gross,
                "operating_income": op_income,
                "net_income": net_income,
                "eps_basic": _safe_float(col.get("Basic EPS")),
                "eps_diluted": _safe_float(col.get("Diluted EPS")),
                "gross_margin": (gross / revenue * 100) if revenue and not _is_nan(gross) and not _is_nan(revenue) else float("nan"),
                "operating_margin": (op_income / revenue * 100) if revenue and not _is_nan(op_income) and not _is_nan(revenue) else float("nan"),
                "net_margin": (net_income / revenue * 100) if revenue and not _is_nan(net_income) and not _is_nan(revenue) else float("nan"),
                "revenue_yoy": float("nan"),
                "profit_yoy": float("nan"),
            })
        return records

    def fetch_cash_flow_statement(self, symbol: str) -> list[dict]:
        """Fetch cash flow statement from yfinance (HK/US/CN)."""
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)
        df = ticker.cash_flow

        if df is None or df.empty:
            raise DataNotFoundError(f"No cash flow statement for {symbol}")

        records = []
        for col_date in df.columns:
            dt = pd.to_datetime(col_date)
            month = dt.month
            quarter = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, f"M{month:02d}")
            period_label = f"{dt.year}{quarter}"

            col = df[col_date]
            operating = _safe_float(col.get("Operating Cash Flow"))
            investing = _safe_float(col.get("Investing Cash Flow"))
            financing = _safe_float(col.get("Financing Cash Flow"))
            capex = _safe_float(col.get("Capital Expenditure"))
            depreciation = _safe_float(col.get("Depreciation And Amortization"))
            free_cf = (operating + capex) if not (_is_nan(operating) or _is_nan(capex)) else float("nan")
            net_cf = (operating + investing + financing) if not any(_is_nan(x) for x in [operating, investing, financing]) else float("nan")

            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "annual",
                "period_end": dt.date().isoformat(),
                "operating_cf": operating,
                "investing_cf": investing,
                "financing_cf": financing,
                "net_cf": net_cf,
                "capex": capex,
                "free_cf": free_cf,
                "depreciation": depreciation,
            })
        return records

    def fetch_earnings_calendar(self, symbol: str) -> list[dict]:
        """Fetch earnings dates with EPS estimates/actuals via yfinance.

        Returns list of dicts: {symbol, report_date, eps_estimate, eps_actual, surprise_pct}.
        """
        yf = _import_yfinance()
        yf_sym = to_yfinance(symbol)
        ticker = yf.Ticker(yf_sym)

        # Distinguish rate-limit from empty-response so the registry can fallback
        # correctly. Previously every exception collapsed to DataNotFoundError,
        # hiding rate-limit signals and preventing fallback to CN akshare.
        try:
            from yfinance.exceptions import YFRateLimitError
        except ImportError:  # older yfinance versions
            YFRateLimitError = ()  # type: ignore[assignment]

        try:
            df = ticker.get_earnings_dates(limit=12)
        except YFRateLimitError as e:
            raise ProviderRateLimitError(
                f"yfinance rate-limited for {symbol} earnings_calendar: {e}"
            ) from e
        except Exception as e:
            # Network / schema error — let registry decide (hard-fail path)
            raise type(e)(f"yfinance earnings_calendar error for {symbol}: {e}") from e

        if df is None or df.empty:
            raise DataNotFoundError(f"No earnings dates for {symbol}")

        records = []
        for idx, row in df.iterrows():
            report_date = idx
            if hasattr(report_date, "date"):
                report_date = report_date.date()
            elif isinstance(report_date, str):
                report_date = datetime.date.fromisoformat(report_date[:10])

            eps_est = row.get("EPS Estimate")
            eps_act = row.get("Reported EPS")
            surprise = row.get("Surprise(%)")

            records.append({
                "symbol": symbol,
                "report_date": str(report_date),
                "eps_estimate": float(eps_est) if pd.notna(eps_est) else None,
                "eps_actual": float(eps_act) if pd.notna(eps_act) else None,
                "surprise_pct": float(surprise) if pd.notna(surprise) else None,
            })

        return records

    def healthcheck(self) -> bool:
        try:
            _import_yfinance()
            return True
        except ImportError:
            return False


def _is_nan(val) -> bool:
    try:
        return math.isnan(val)
    except (TypeError, ValueError):
        return True


def _safe_float(val) -> float:
    if val is None:
        return float("nan")
    try:
        f = float(val)
        return f if not math.isnan(f) else float("nan")
    except (ValueError, TypeError):
        return float("nan")
