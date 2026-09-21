"""FredProvider — US macro indicators from FRED (Federal Reserve Economic Data).

Fetches 9 key series: interest rates, inflation (YoY), employment, and USD index.
Requires FRED_API_KEY environment variable. Returns list[dict] matching MacroStore schema.

Reference: https://fred.stlouisfed.org/fred/series/observations
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import urllib.parse
import urllib.request

from market_data_kit.providers.circuit_breaker import CircuitBreaker

__all__ = ["FredProvider"]

logger = logging.getLogger(__name__)

# FRED series: indicator_name → (series_id, unit, fetch_limit)
# Daily rate series need ~5 business days; YoY need 14 months; monthly need 3.
_SERIES: dict[str, tuple[str, str, int]] = {
    "fed_funds_rate": ("DFF", "%", 5),
    "treasury_10y": ("DGS10", "%", 5),
    "treasury_2y": ("DGS2", "%", 5),
    "yield_curve_spread": ("T10Y2Y", "%", 5),
    "cpi_yoy": ("CPIAUCSL", "%", 14),
    "pce_yoy": ("PCEPI", "%", 14),
    "unemployment_rate": ("UNRATE", "%", 3),
    "nonfarm_payrolls": ("PAYEMS", "千人", 3),
    "usd_index": ("DTWEXBGS", "index", 5),
}

# Series that require Year-over-Year percentage calculation
_YOY_SERIES = {"cpi_yoy", "pce_yoy"}

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_series_raw(series_id: str, api_key: str, limit: int = 14) -> list[dict[str, str]]:
    """Fetch recent observations for a single FRED series.

    Returns list of {"date": "YYYY-MM-DD", "value": "..."} dicts, sorted desc by date.
    """
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    })
    url = f"{_BASE_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "market-data-kit/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("observations", [])


def _latest_value(observations: list[dict[str, str]]) -> tuple[float | None, str | None]:
    """Extract latest non-'.' numeric value and its date from observations."""
    for obs in observations:
        val = obs.get("value", ".")
        if val != ".":
            try:
                return float(val), obs.get("date")
            except (ValueError, TypeError):
                continue
    return None, None


def _calc_yoy_pct(observations: list[dict[str, str]]) -> tuple[float | None, str | None]:
    """Calculate year-over-year % change from monthly FRED data.

    Matches the same month from the prior year (e.g., 2026-02 vs 2025-02).
    Needs at least 13 months of data. Returns (percentage, latest_date).
    """
    latest: float | None = None
    latest_date: str | None = None
    latest_month: str | None = None

    for obs in observations:
        val_str = obs.get("value", ".")
        if val_str == ".":
            continue
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            continue

        if latest is None:
            latest = val
            latest_date = obs["date"]
            latest_month = latest_date[5:7] if len(latest_date) >= 7 else None
        elif latest_month and len(obs["date"]) >= 7:
            obs_month = obs["date"][5:7]
            obs_year = obs["date"][:4]
            latest_year = latest_date[:4]  # type: ignore[union-attr]
            if obs_month == latest_month and obs_year < latest_year:
                if val != 0:
                    return round((latest - val) / val * 100, 2), latest_date
                return None, latest_date

    return None, latest_date


class FredProvider:
    """Provider for US macro indicators from FRED."""

    name = "fred"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("FRED_API_KEY", "").strip()
        self._cb = CircuitBreaker("fred", failure_threshold=3, cooldown_seconds=600)

    def fetch_macro(self, market: str = "US") -> list[dict]:
        """Fetch US macro indicators from FRED.

        Returns list of dicts matching MacroStore schema:
            {indicator, date, value, unit, source}

        Returns empty list if API key is missing or all series fail.
        """
        if market.upper() != "US":
            return []

        if not self._api_key:
            logger.info("FRED_API_KEY not set, skipping US macro data")
            return []

        if not self._cb.allow_request():
            logger.warning("FRED circuit breaker open, skipping")
            return []

        results: list[dict] = []
        errors = 0

        for indicator_name, (series_id, unit, limit) in _SERIES.items():
            try:
                obs = _fetch_series_raw(series_id, self._api_key, limit=limit)

                if indicator_name in _YOY_SERIES:
                    value, date_str = _calc_yoy_pct(obs)
                else:
                    value, date_str = _latest_value(obs)

                if value is not None and date_str is not None:
                    results.append({
                        "indicator": indicator_name,
                        "date": datetime.date.fromisoformat(date_str),
                        "value": value,
                        "unit": unit,
                        "source": "fred",
                    })
                    logger.debug("FRED %s (%s) = %s", indicator_name, series_id, value)
                else:
                    logger.debug("FRED %s (%s): no valid data", indicator_name, series_id)

            except Exception as exc:
                errors += 1
                logger.warning("FRED %s (%s) failed: %s", indicator_name, series_id, exc)

        if errors >= len(_SERIES):
            self._cb.record_failure()
            logger.error("All FRED series failed")
            return []

        if results:
            self._cb.record_success()

        return results

    def healthcheck(self) -> bool:
        return bool(self._api_key)
