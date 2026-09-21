"""Akshare provider — CN/HK market data via akshare library."""
from __future__ import annotations

import datetime
import logging
import math

import pandas as pd

from market_data_kit.symbols import normalize, market as get_market, exchange, to_akshare
from market_data_kit.providers.proxy_cleanup import clear_proxy
from market_data_kit.providers.base import DataNotFoundError

__all__ = ["AkshareProvider"]

logger = logging.getLogger(__name__)


def _import_ak():
    """Lazy import akshare with proxy cleanup."""
    try:
        with clear_proxy():
            import akshare as ak
        return ak
    except ImportError:
        raise ImportError("akshare not installed. Run: pip install market-data-kit[akshare]")


class AkshareProvider:
    name = "akshare"

    def __init__(self) -> None:
        self._us_em_cache: dict[str, str] | None = None

    def fetch_klines(self, symbol: str, days: int,
                     end_date: datetime.date | None = None, adjust: str = "none") -> pd.DataFrame:
        if adjust not in {"none", "qfq", "hfq"}:
            raise ValueError("Unknown adjustment")
        mkt = get_market(symbol)
        if mkt == "IDX":
            if adjust != "none":
                raise NotImplementedError("Index adapter supports only none")
            if not to_akshare(symbol).isdigit():
                raise NotImplementedError("Only numeric indices supported by akshare")
            result = self._fetch_idx_klines(symbol, days, end_date)
        elif mkt in {"CN", "HK", "US"}:
            result = getattr(self, f"_fetch_{mkt.lower()}_klines")(
                symbol, days, end_date, "" if adjust == "none" else adjust)
        else:
            raise NotImplementedError(f"akshare does not support {mkt} klines")
        result["adjust"] = adjust
        if "adjust_factor" in result:
            result["adjust_factor"] = 1.0 if adjust == "none" else float("nan")
            result["raw_close"] = result["close"] if adjust == "none" else float("nan")
        return result

    def _fetch_cn_klines(self, symbol, days, end_date, adjust=""):
        ak = _import_ak()
        code = to_akshare(symbol)
        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))

        with clear_proxy():
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust=adjust,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )

        if df is None or df.empty:
            raise DataNotFoundError(f"No CN kline data for {symbol}")

        return self._map_cn_columns(df, symbol)

    def _fetch_hk_klines(self, symbol, days, end_date, adjust=""):
        ak = _import_ak()
        code = to_akshare(symbol)  # "00700"
        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))

        with clear_proxy():
            # Try stock_hk_hist (newer) then stock_hk_daily (older)
            for func_name in ["stock_hk_hist", "stock_hk_daily"]:
                fn = getattr(ak, func_name, None)
                if fn is None:
                    continue
                try:
                    df = fn(symbol=code, adjust=adjust)
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue
            else:
                raise DataNotFoundError(f"No HK kline data for {symbol}")

        return self._map_hk_columns(df, symbol, start_date, end_date)

    def _fetch_idx_klines(self, symbol, days, end_date):
        """Fetch CN A-share index klines via akshare."""
        ak = _import_ak()
        code = to_akshare(symbol)  # "000300"
        # stock_zh_index_daily needs exchange prefix: sh000300, sz399006
        exch = exchange(symbol)
        if exch == "INDEX":
            from market_data_kit.symbols import to_wind
            wind_sym = to_wind(symbol)  # "000300.SH"
            wind_exch = wind_sym.split(".")[-1].lower()  # "sh"
            ak_symbol = f"{wind_exch}{code}"  # "sh000300"
        else:
            ak_symbol = code

        with clear_proxy():
            df = ak.stock_zh_index_daily(symbol=ak_symbol)

        if df is None or df.empty:
            raise DataNotFoundError(f"No index kline data for {symbol}")

        # Filter by date range
        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

        if df.empty:
            raise DataNotFoundError(f"No index kline data for {symbol} in date range")

        return self._map_idx_columns(df, symbol)

    def _resolve_us_em_code(self, ticker: str) -> str | None:
        """Look up eastmoney internal code for a US ticker.

        akshare's stock_us_hist requires the eastmoney code (e.g. '105.AAPL'),
        not the bare ticker. Cache the full us_spot table on first call.

        Returns the eastmoney code or None if ticker is unknown.
        """
        if self._us_em_cache is None:
            ak = _import_ak()
            with clear_proxy():
                spot = ak.stock_us_spot_em()
            self._us_em_cache = {
                row["代码"].split(".", 1)[-1]: row["代码"]
                for _, row in spot.iterrows()
            }
        return self._us_em_cache.get(ticker)

    def _fetch_us_klines(self, symbol: str, days: int,
                         end_date: datetime.date | None, adjust="") -> pd.DataFrame:
        """Fetch US klines via akshare stock_us_hist (qfq adjusted).

        akshare's US ticker resolution requires an eastmoney internal code.
        Lookup happens via stock_us_spot_em (cached on first call).
        """
        ak = _import_ak()
        if end_date is None:
            end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=int(days * 1.5))

        raw_ticker = symbol.split(".", 1)[1]  # "AAPL" from "US.AAPL"
        em_code = self._resolve_us_em_code(raw_ticker)
        if em_code is None:
            raise DataNotFoundError(
                f"akshare cannot resolve US ticker {raw_ticker} to eastmoney code"
            )

        with clear_proxy():
            df = ak.stock_us_hist(
                symbol=em_code, period="daily", adjust=adjust,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )

        if df is None or df.empty:
            raise DataNotFoundError(f"No US kline data for {symbol}")

        return self._map_us_columns(df, symbol)

    def _map_us_columns(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Map akshare stock_us_hist Chinese columns to MDK schema.

        Note: stock_us_hist with adjust='qfq' returns adjusted close. Without
        a parallel raw fetch, we set adjust_factor=1.0 (placeholder) and
        raw_close=close. Future refinement should compute true adjust_factor
        by cross-fetching with adjust='' (unadjusted).
        """
        exch = exchange(symbol) or ""
        out = pd.DataFrame({
            "symbol": symbol,
            "exchange": exch,
            "date": pd.to_datetime(df["日期"]).dt.date.values,
            "open": df["开盘"].astype(float).values,
            "high": df["最高"].astype(float).values,
            "low": df["最低"].astype(float).values,
            "close": df["收盘"].astype(float).values,
            "volume": df["成交量"].astype("int64").values,
            "turnover": df["成交额"].astype(float).values,
            "pct_change": df["涨跌幅"].astype(float).values,
            "prev_close": df["收盘"].shift(1).astype(float).values,
            "turnover_rate": df["换手率"].astype(float).values,
            "pe_ratio": float("nan"),
            "adjust": "qfq",
            "adjust_factor": 1.0,
            "raw_close": df["收盘"].astype(float).values,
        })
        out = out.dropna(subset=["close"])
        return out.sort_values("date").reset_index(drop=True)

    def _map_idx_columns(self, df, symbol):
        # stock_zh_index_daily returns English columns: date, open, high, low, close, volume
        # Also handle Chinese columns from stock_zh_index_daily_em as fallback
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "turnover", "涨跌幅": "pct_change",
        }
        df = df.rename(columns=col_map)
        n = len(df)
        result = pd.DataFrame()
        result["symbol"] = [symbol] * n
        result["exchange"] = ["INDEX"] * n
        result["date"] = pd.to_datetime(df["date"]).dt.date.values if not pd.api.types.is_object_dtype(df["date"]) else df["date"].values
        for col in ["open", "high", "low", "close"]:
            result[col] = df[col].astype(float).values if col in df.columns else float("nan")
        result["volume"] = df["volume"].astype("int64").values if "volume" in df.columns else 0
        result["turnover"] = df["turnover"].astype(float).values if "turnover" in df.columns else float("nan")
        result["pct_change"] = df["pct_change"].astype(float).values if "pct_change" in df.columns else float("nan")
        result["prev_close"] = float("nan")
        result["turnover_rate"] = float("nan")
        result["pe_ratio"] = float("nan")
        result["adjust"] = "none"
        return result.reset_index(drop=True)

    def _map_cn_columns(self, df, symbol):
        exch = exchange(symbol)
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "turnover", "涨跌幅": "pct_change", "换手率": "turnover_rate",
        }
        df = df.rename(columns=col_map)
        n = len(df)
        result = pd.DataFrame()
        result["symbol"] = [symbol] * n
        result["exchange"] = [exch] * n
        result["date"] = pd.to_datetime(df["date"]).dt.date.values
        for col in ["open", "high", "low", "close"]:
            result[col] = df[col].astype(float).values if col in df.columns else float("nan")
        result["volume"] = (df["volume"].astype(float) * 100).round().astype("int64").values if "volume" in df.columns else 0
        result["turnover"] = df["turnover"].astype(float).values if "turnover" in df.columns else float("nan")
        result["pct_change"] = df["pct_change"].astype(float).values if "pct_change" in df.columns else float("nan")
        result["prev_close"] = float("nan")
        result["turnover_rate"] = df["turnover_rate"].astype(float).values if "turnover_rate" in df.columns else float("nan")
        result["pe_ratio"] = float("nan")
        result["adjust"] = "qfq"
        return result.reset_index(drop=True)

    def _map_hk_columns(self, df, symbol, start_date, end_date):
        exch = "HKEX"
        # HK akshare columns may be Chinese or English depending on version
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "turnover", "涨跌幅": "pct_change",
        }
        df = df.rename(columns=col_map)
        if "date" not in df.columns:
            # Some versions use lowercase English
            for c in df.columns:
                if "date" in c.lower():
                    df = df.rename(columns={c: "date"})
                    break

        n = len(df)
        result = pd.DataFrame()
        result["symbol"] = [symbol] * n
        result["exchange"] = [exch] * n
        result["date"] = pd.to_datetime(df["date"]).dt.date.values
        for col in ["open", "high", "low", "close"]:
            result[col] = df[col].astype(float).values if col in df.columns else float("nan")
        result["volume"] = df["volume"].astype(int).values if "volume" in df.columns else 0
        result["turnover"] = df["turnover"].astype(float).values if "turnover" in df.columns else float("nan")
        result["pct_change"] = df["pct_change"].astype(float).values if "pct_change" in df.columns else float("nan")
        result["prev_close"] = float("nan")
        result["turnover_rate"] = float("nan")
        result["pe_ratio"] = float("nan")
        result["adjust"] = "qfq"

        # Filter date range
        result = result[(result["date"] >= start_date) & (result["date"] <= end_date)]
        return result.sort_values("date").reset_index(drop=True)

    def fetch_fundamentals(self, symbol: str) -> dict:
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"akshare fundamentals only for CN, got {mkt}")

        ak = _import_ak()
        code = to_akshare(symbol)

        # API name probing: akshare renames functions across versions
        import datetime as _dt
        current_year = str(_dt.date.today().year - 1)  # 去年起有完整数据
        candidates = [
            ("stock_a_lg_indicator", {"symbol": code}),
            ("stock_financial_analysis_indicator", {"symbol": code, "start_year": current_year}),
        ]

        df = None
        with clear_proxy():
            for func_name, kwargs in candidates:
                fn = getattr(ak, func_name, None)
                if fn is None:
                    continue
                try:
                    df = fn(**kwargs)
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue

        if df is None or df.empty:
            raise DataNotFoundError(f"No fundamentals for {symbol}")

        latest = df.iloc[-1]
        # Column names vary: old API uses English, new uses Chinese
        return {
            "symbol": symbol,
            "pe_ratio": _safe_float(latest.get("pe") or latest.get("pe_ttm")),
            "pb_ratio": _safe_float(latest.get("pb") or latest.get("pb_mrq")),
            "roe": _safe_float(latest.get("净资产收益率(%)")),
            "gross_margin": _safe_float(latest.get("销售毛利率(%)")),
            "net_margin": _safe_float(latest.get("销售净利率(%)")),
            "eps": _safe_float(latest.get("摊薄每股收益(元)") or latest.get("eps")),
            "debt_ratio": _safe_float(latest.get("资产负债率(%)")),
            "revenue_yoy": _safe_float(latest.get("主营业务收入增长率(%)")),
            "profit_yoy": _safe_float(latest.get("净利润增长率(%)")),
            "market_cap": float("nan"),  # Assets are not market value; source units vary.
            "circ_market_cap": float("nan"),
        }

    def fetch_snapshot(self, symbols):
        raise NotImplementedError("akshare does not support real-time snapshots")

    def fetch_capital_flow(self, symbol, days=5):
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"akshare capital_flow only for CN, got {mkt}")

        ak = _import_ak()
        code = to_akshare(symbol)
        exch_map = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
        exch = exch_map.get(exchange(symbol), "sh")

        with clear_proxy():
            try:
                df = ak.stock_individual_fund_flow(stock=code, market=exch)
            except Exception as e:
                raise DataNotFoundError(f"No capital flow for {symbol}: {e}")

        if df is None or df.empty:
            raise DataNotFoundError(f"No capital flow for {symbol}")

        rows = []
        for _, r in df.iterrows():
            rows.append({
                "symbol": symbol,
                "date": pd.to_datetime(r["日期"]).date(),
                "super_in": _safe_float(r.get("超大单净流入-净额", 0)),
                "big_in": _safe_float(r.get("大单净流入-净额", 0)),
                "mid_in": _safe_float(r.get("中单净流入-净额", 0)),
                "small_in": _safe_float(r.get("小单净流入-净额", 0)),
                "main_in": _safe_float(r.get("主力净流入-净额", 0)),
            })

        result = pd.DataFrame(rows)
        if days > 0:
            result = result.sort_values("date").tail(days)
        return result.reset_index(drop=True)

    def fetch_plates(self, symbol):
        raise NotImplementedError("akshare plates not in Phase 2 scope")

    def fetch_balance_sheet(self, symbol: str) -> list[dict]:
        """Fetch balance sheet data for a CN stock via akshare."""
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"akshare balance_sheet only for CN, got {mkt}")

        ak = _import_ak()
        code = exchange(symbol) + to_akshare(symbol)

        with clear_proxy():
            try:
                df = ak.stock_balance_sheet_by_report_em(symbol=code)
            except Exception:
                try:
                    df = ak.stock_balance_sheet_by_yearly_em(symbol=code)
                except Exception:
                    raise DataNotFoundError(f"No balance sheet for {symbol}")

        if df is None or df.empty:
            raise DataNotFoundError(f"No balance sheet for {symbol}")

        records = []
        for _, row in df.iterrows():
            period_label = _parse_period(row)
            if not period_label:
                continue

            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "point_in_time",
                "period_end": _period_end(row),
                "total_assets": _safe_float(_first(row, "TOTAL_ASSETS", "资产总计")),
                "total_liabilities": _safe_float(_first(row, "TOTAL_LIABILITIES", "负债合计")),
                "equity": _safe_float(_first(row, "TOTAL_EQUITY", "所有者权益合计")),
                "current_assets": _safe_float(_first(row, "TOTAL_CURRENT_ASSETS", "流动资产合计")),
                "current_liabilities": _safe_float(_first(row, "TOTAL_CURRENT_LIAB", "流动负债合计")),
                "cash": _safe_float(_first(row, "MONETARYFUNDS", "货币资金")),
                "inventory": _safe_float(_first(row, "INVENTORY", "存货")),
                "receivables": _safe_float(_first(row, "ACCOUNTS_RECE", "应收账款")),
            })
        return records

    def fetch_income_statement(self, symbol: str) -> list[dict]:
        """Fetch income statement for a CN stock via akshare."""
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"akshare income_statement only for CN, got {mkt}")

        ak = _import_ak()
        code = exchange(symbol) + to_akshare(symbol)

        with clear_proxy():
            try:
                df = ak.stock_profit_sheet_by_report_em(symbol=code)
            except Exception:
                try:
                    df = ak.stock_profit_sheet_by_yearly_em(symbol=code)
                except Exception:
                    raise DataNotFoundError(f"No income statement for {symbol}")

        if df is None or df.empty:
            raise DataNotFoundError(f"No income statement for {symbol}")

        records = []
        for _, row in df.iterrows():
            period_label = _parse_period(row)
            if not period_label:
                continue

            revenue = _safe_float(_first(row, "TOTAL_OPERATE_INCOME", "营业总收入"))
            cost = _safe_float(_first(row, "OPERATE_COST", "营业成本"))
            gross_profit = revenue - cost if not (_is_nan(revenue) or _is_nan(cost)) else float("nan")
            net_income = _safe_float(_first(row, "NETPROFIT", "净利润"))
            op_income = _safe_float(_first(row, "OPERATE_PROFIT", "营业利润"))

            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "year_to_date",
                "period_end": _period_end(row),
                "revenue": revenue,
                "cost_of_revenue": cost,
                "gross_profit": gross_profit,
                "operating_income": op_income,
                "net_income": net_income,
                "eps_basic": _safe_float(_first(row, "BASIC_EPS", "基本每股收益(元)")),
                "eps_diluted": _safe_float(_first(row, "DILUTED_EPS", "稀释每股收益(元)")),
                "gross_margin": (gross_profit / revenue * 100) if revenue and not _is_nan(gross_profit) and not _is_nan(revenue) else float("nan"),
                "operating_margin": (op_income / revenue * 100) if revenue and not _is_nan(op_income) and not _is_nan(revenue) else float("nan"),
                "net_margin": (net_income / revenue * 100) if revenue and not _is_nan(net_income) and not _is_nan(revenue) else float("nan"),
                "revenue_yoy": float("nan"),
                "profit_yoy": float("nan"),
            })
        return records

    def fetch_cash_flow_statement(self, symbol: str) -> list[dict]:
        """Fetch cash flow statement for a CN stock via akshare."""
        mkt = get_market(symbol)
        if mkt != "CN":
            raise NotImplementedError(f"akshare cash_flow_statement only for CN, got {mkt}")

        ak = _import_ak()
        code = exchange(symbol) + to_akshare(symbol)

        with clear_proxy():
            try:
                df = ak.stock_cash_flow_sheet_by_report_em(symbol=code)
            except Exception:
                try:
                    df = ak.stock_cash_flow_sheet_by_yearly_em(symbol=code)
                except Exception:
                    raise DataNotFoundError(f"No cash flow statement for {symbol}")

        if df is None or df.empty:
            raise DataNotFoundError(f"No cash flow statement for {symbol}")

        records = []
        for _, row in df.iterrows():
            period_label = _parse_period(row)
            if not period_label:
                continue

            operating = _safe_float(_first(row, "NETCASH_OPERATE", "经营活动产生的现金流量净额"))
            investing = _safe_float(_first(row, "NETCASH_INVEST", "投资活动产生的现金流量净额"))
            financing = _safe_float(_first(row, "NETCASH_FINANCE", "筹资活动产生的现金流量净额"))
            net = _safe_float(_first(row, "CCE_ADD", "现金及现金等价物净增加额"))
            capex_raw = _safe_float(_first(row, "BUY_FIX_ASSETS_OTHER", "购建固定资产、无形资产和其他长期资产支付的现金"))
            capex = -abs(capex_raw) if not _is_nan(capex_raw) else float("nan")
            depreciation = _safe_float(_first(row, "FIXED_ASSETS_DEPRECIATION", "固定资产折旧"))
            free_cf = (operating + capex) if not (_is_nan(operating) or _is_nan(capex)) else float("nan")

            records.append({
                "symbol": symbol,
                "period": period_label,
                "period_type": "year_to_date",
                "period_end": _period_end(row),
                "operating_cf": operating,
                "investing_cf": investing,
                "financing_cf": financing,
                "net_cf": net,
                "capex": capex,
                "free_cf": free_cf,
                "depreciation": depreciation,
            })
        return records

    def fetch_northbound_flow(self, market: str) -> list[dict]:
        """Fetch northbound/southbound capital flow summary (today) via eastmoney.

        Returns list of dicts with: date, direction, board, net_buy_yi, index_name, index_pct.
        """
        ak = _import_ak()
        today = datetime.date.today().isoformat()

        with clear_proxy():
            try:
                df = ak.stock_hsgt_fund_flow_summary_em()
            except (AttributeError, Exception):
                try:
                    df = ak.stock_hsgt_board_rank_em(symbol="全部")
                except Exception:
                    raise DataNotFoundError("northbound flow: no akshare API available")

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.iterrows():
            net = float(row.get("成交净买额", 0) or 0)
            direction_cn = str(row.get("资金方向", ""))
            direction = "northbound" if direction_cn == "北向" else "southbound" if direction_cn == "南向" else direction_cn
            records.append({
                "date": today,
                "direction": direction,
                "board": str(row.get("板块", "")),
                "net_buy_yi": round(net, 2),
                "index_name": str(row.get("相关指数", "")),
                "index_pct": round(float(row.get("指数涨跌幅", 0) or 0), 2),
            })

        return records

    def fetch_earnings_calendar(self, symbol: str) -> list[dict]:
        """Fetch earnings disclosure dates for A-shares via cninfo (巨潮).

        Returns list of dicts matching the yfinance shape for interop:
          {symbol, report_date, eps_estimate, eps_actual, surprise_pct}

        EPS fields are always None for this provider (cninfo disclosure
        dataset is date-centric, not EPS-centric). Callers that only need
        disclosure dates (e.g. watchpoints) get what they need; callers
        that need EPS data should remain on yfinance for US.

        Strategy: iterate the last 4 quarter-end periods; for each period
        issue one stock_report_disclosure(period) query filtered to our
        symbol's 股票代码. Collect 实际披露 (actual disclosure) when
        present, otherwise 首次预约 (initial scheduled date) so we can
        still give a forward-looking date for an un-disclosed period.
        """
        mkt = get_market(symbol)
        if mkt != "CN":
            raise DataNotFoundError(
                f"akshare earnings_calendar only supports CN (got {mkt} for {symbol})"
            )

        ak = _import_ak()
        code = symbol.split(".")[-1]  # "CN.600519" → "600519"

        # Compute most recent 4 quarter-end periods relative to today.
        today = datetime.date.today()
        year = today.year
        # Iterate the past ~2 years of quarter tags descending; stop when we
        # have 4 that have already passed their period-end date.
        period_end_of = {
            "一季": (3, 31),
            "半年报": (6, 30),
            "三季": (9, 30),
            "年报": (12, 31),
        }
        candidates: list[str] = []
        for y in (year, year - 1, year - 2):
            for tag in ("年报", "三季", "半年报", "一季"):  # descending within a year
                m, d = period_end_of[tag]
                # Skip future periods; we want ones whose end date has passed
                if datetime.date(y, m, d) > today:
                    continue
                candidates.append(f"{y}{tag}")
                if len(candidates) >= 4:
                    break
            if len(candidates) >= 4:
                break

        results: list[dict] = []
        with clear_proxy():
            for period in candidates:
                try:
                    df = ak.stock_report_disclosure(market="沪深京", period=period)
                except Exception as e:
                    logger.debug("akshare stock_report_disclosure(%s) failed: %s", period, e)
                    continue
                if df is None or df.empty:
                    continue
                row = df[df["股票代码"] == code]
                if row.empty:
                    continue
                row = row.iloc[0]
                # Prefer actual disclosure date; fallback to first scheduled
                rd = row.get("实际披露")
                if _is_nat(rd):
                    rd = row.get("首次预约")
                if _is_nat(rd):
                    continue
                results.append({
                    "symbol": symbol,
                    "report_date": str(rd)[:10],
                    "eps_estimate": None,
                    "eps_actual": None,
                    "surprise_pct": None,
                })

        if not results:
            raise DataNotFoundError(f"akshare earnings_calendar: no disclosures for {symbol}")
        return results

    def healthcheck(self) -> bool:
        try:
            _import_ak()
            return True
        except ImportError:
            return False


def _safe_float(val) -> float:
    if val is None:
        return float("nan")
    try:
        return float(val)
    except (ValueError, TypeError):
        return float("nan")


def _is_nan(val) -> bool:
    try:
        return math.isnan(val)
    except (TypeError, ValueError):
        return True


def _is_nat(val) -> bool:
    """True if val is NaT, NaN, None, or 'NaT' string."""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() in ("", "NaT", "nan", "None")
    try:
        return pd.isna(val)
    except (TypeError, ValueError):
        return False


def _first(row, *keys):
    """First present field; zero is a value, not a reason to change sources."""
    for key in keys:
        value = row.get(key)
        if value is not None and not pd.isna(value):
            return value
    return None


def _parse_period(row) -> str | None:
    """Prefer provider report dates over Chinese period labels."""
    for key in ("REPORT_DATE", "REPORTDATE", "REPORT_DATE_NAME"):
        raw = row.get(key)
        if raw is None or pd.isna(raw):
            continue
        value = pd.to_datetime(str(raw), errors="coerce")
        if not pd.isna(value):
            return f"{value.year}Q{(value.month - 1) // 3 + 1}"
    return None


def _period_end(row):
    for key in ("REPORT_DATE", "REPORTDATE", "REPORT_DATE_NAME"):
        value = pd.to_datetime(str(row.get(key, "")), errors="coerce")
        if not pd.isna(value):
            return value.date().isoformat()
    return None
