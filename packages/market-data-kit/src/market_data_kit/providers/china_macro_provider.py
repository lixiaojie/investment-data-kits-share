"""ChinaMacroProvider — China macro economic data via akshare.

Provides latest values for key indicators: LPR, PMI, CPI, PPI, M2.
Returns list[dict] matching MacroStore schema (indicator, date, value, unit, source).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from market_data_kit.providers.proxy_cleanup import clear_proxy

__all__ = ["ChinaMacroProvider"]

logger = logging.getLogger(__name__)


def _import_ak():
    """Lazy import akshare with proxy cleanup."""
    try:
        with clear_proxy():
            import akshare as ak
        return ak
    except ImportError:
        raise ImportError("akshare not installed. Run: pip install market-data-kit[akshare]")


def _safe_float(val: Any) -> float | None:
    """Convert value to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_date(val: Any) -> datetime.date | None:
    """Parse a date value from akshare DataFrame row."""
    if val is None:
        return None
    # pandas Timestamp has .date() method — check before plain datetime.date
    if hasattr(val, "date") and callable(val.date):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    try:
        s = str(val).strip()[:10]
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# --- Indicator fetchers ---
# Each returns a list of MacroPoint dicts (usually 1-2 items).


def _fetch_lpr(ak: Any) -> list[dict]:
    """Fetch latest LPR rates (1Y and 5Y)."""
    try:
        with clear_proxy():
            df = ak.macro_china_lpr()
        if df is None or df.empty:
            return []
        last_row = df.iloc[-1]
        date_val = _parse_date(last_row.iloc[0]) or datetime.date.today()

        # Find LPR 1Y and 5Y columns by name pattern
        lpr_1y = None
        lpr_5y = None
        for col in df.columns:
            col_lower = str(col).lower().replace(" ", "")
            if "1" in col_lower and "lpr" in col_lower:
                lpr_1y = _safe_float(last_row[col])
            elif "5" in col_lower and "lpr" in col_lower:
                lpr_5y = _safe_float(last_row[col])

        # Fallback: positional columns
        if lpr_1y is None and lpr_5y is None and len(df.columns) >= 3:
            lpr_1y = _safe_float(last_row.iloc[1])
            lpr_5y = _safe_float(last_row.iloc[2])

        results = []
        if lpr_1y is not None and 0 < lpr_1y < 20:
            results.append({
                "indicator": "lpr_1y",
                "date": date_val,
                "value": lpr_1y,
                "unit": "%",
                "source": "akshare",
            })
        if lpr_5y is not None and 0 < lpr_5y < 20:
            results.append({
                "indicator": "lpr_5y",
                "date": date_val,
                "value": lpr_5y,
                "unit": "%",
                "source": "akshare",
            })
        return results
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("China LPR fetch failed: %s", exc)
        return []


def _fetch_pmi(ak: Any) -> list[dict]:
    """Fetch latest manufacturing PMI."""
    try:
        with clear_proxy():
            df = ak.macro_china_pmi()
        if df is None or df.empty:
            return []
        last_row = df.iloc[-1]
        date_val = _parse_date(last_row.iloc[0]) or datetime.date.today()

        val = None
        for col in df.columns:
            col_str = str(col)
            if "制造业" in col_str or "pmi" in col_str.lower():
                val = _safe_float(last_row[col])
                if val is not None and 20 < val < 80:
                    break
                val = None

        # Fallback positional
        if val is None and len(df.columns) >= 2:
            val = _safe_float(last_row.iloc[1])
            if val is not None and not (20 < val < 80):
                val = None

        if val is not None:
            return [{
                "indicator": "pmi_manufacturing",
                "date": date_val,
                "value": val,
                "unit": "",
                "source": "akshare",
            }]
        return []
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("China PMI fetch failed: %s", exc)
        return []


def _parse_cn_month(s: str) -> datetime.date | None:
    """Parse '2026年02月份' → datetime.date(2026, 2, 1)."""
    import re
    m = re.match(r"(\d{4})年(\d{1,2})月", str(s))
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), 1)
    return None


def _fetch_cpi(ak: Any) -> list[dict]:
    """Fetch latest CPI year-over-year change."""
    try:
        with clear_proxy():
            df = ak.macro_china_cpi()
        if df is None or df.empty:
            return []
        first_row = df.iloc[0]
        date_val = _parse_cn_month(first_row.get("月份", "")) or datetime.date.today()

        val = None
        if "全国-同比增长" in df.columns:
            val = _safe_float(first_row["全国-同比增长"])

        if val is None:
            for col in df.columns:
                col_str = str(col)
                if "同比" in col_str and "全国" in col_str:
                    val = _safe_float(first_row[col])
                    if val is not None and -20 < val < 30:
                        break
                    val = None

        if val is not None and -20 < val < 30:
            return [{
                "indicator": "cn_cpi_yoy",
                "date": date_val,
                "value": val,
                "unit": "%",
                "source": "akshare",
            }]
        return []
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("China CPI fetch failed: %s", exc)
        return []


def _fetch_ppi(ak: Any) -> list[dict]:
    """Fetch latest PPI year-over-year change."""
    try:
        with clear_proxy():
            df = ak.macro_china_ppi()
        if df is None or df.empty:
            return []
        last_row = df.iloc[-1]
        date_val = _parse_date(last_row.iloc[0]) or datetime.date.today()

        val = None
        for col in df.columns:
            col_str = str(col)
            if "同比" in col_str or "当月" in col_str:
                val = _safe_float(last_row[col])
                if val is not None and -30 < val < 30:
                    break
                val = None

        if val is None and len(df.columns) >= 2:
            val = _safe_float(last_row.iloc[1])
            if val is not None and not (-30 < val < 30):
                val = None

        if val is not None:
            return [{
                "indicator": "cn_ppi_yoy",
                "date": date_val,
                "value": val,
                "unit": "%",
                "source": "akshare",
            }]
        return []
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("China PPI fetch failed: %s", exc)
        return []


def _fetch_m2(ak: Any) -> list[dict]:
    """Fetch latest M2 money supply growth rate."""
    try:
        with clear_proxy():
            df = ak.macro_china_money_supply()
        if df is None or df.empty:
            return []
        last_row = df.iloc[-1]
        date_val = _parse_date(last_row.iloc[0]) or datetime.date.today()

        val = None
        for col in df.columns:
            col_str = str(col)
            if "m2" in col_str.lower() and ("同比" in col_str or "增长" in col_str or "yoy" in col_str.lower()):
                val = _safe_float(last_row[col])
                if val is not None:
                    break

        # Fallback: M2 YoY is often in column index 2 or 3
        if val is None:
            for idx in [2, 3, 1]:
                if idx < len(df.columns):
                    val = _safe_float(last_row.iloc[idx])
                    if val is not None and 0 < val < 30:
                        break
                    val = None

        if val is not None:
            return [{
                "indicator": "cn_m2_yoy",
                "date": date_val,
                "value": val,
                "unit": "%",
                "source": "akshare",
            }]
        return []
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("China M2 fetch failed: %s", exc)
        return []


class ChinaMacroProvider:
    """China macro economic data provider via akshare.

    Fetches LPR, PMI, CPI, PPI, M2 indicators. Each call returns
    list[dict] matching MacroStore schema.
    """

    name = "china_macro"

    _FETCHERS = [
        ("LPR", _fetch_lpr),
        ("PMI", _fetch_pmi),
        ("CPI", _fetch_cpi),
        ("PPI", _fetch_ppi),
        ("M2", _fetch_m2),
    ]

    def fetch_macro(self, market: str = "CN") -> list[dict]:
        """Fetch latest China macro indicators.

        Args:
            market: Must be "CN". Raises ValueError for other markets.

        Returns:
            List of dicts with keys: indicator, date, value, unit, source.
            Empty list if akshare unavailable or all calls fail.
        """
        if market.upper() != "CN":
            raise ValueError(f"ChinaMacroProvider only supports CN market, got {market}")

        try:
            ak = _import_ak()
        except ImportError:
            logger.warning("akshare not available, cannot fetch China macro data")
            return []

        results: list[dict] = []
        errors = 0

        for label, fetcher in self._FETCHERS:
            try:
                points = fetcher(ak)
                results.extend(points)
                if points:
                    logger.debug("China %s: %d points", label, len(points))
            except ImportError:
                raise
            except Exception as exc:
                errors += 1
                logger.warning("China %s fetch failed: %s", label, exc)

        if errors >= len(self._FETCHERS):
            logger.error("All China macro fetchers failed")

        indicators = [r["indicator"] for r in results]
        logger.info("China macro: fetched %d indicators %s", len(indicators), indicators)
        return results

    def healthcheck(self) -> bool:
        """Check if akshare is importable."""
        try:
            _import_ak()
            return True
        except ImportError:
            return False
