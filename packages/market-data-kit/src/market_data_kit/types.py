"""Core data structures for market-data-kit.

OHLCV, CapitalFlow and Plate are TypedDict (dict-compatible, good for DataFrame rows).
Snapshot and Fundamentals are dataclass (object-oriented, good for single entities).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TypedDict


class OHLCV(TypedDict):
    """A single K-line bar. Matches the Parquet schema."""
    symbol: str
    exchange: str
    date: datetime.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float
    pct_change: float
    prev_close: float
    turnover_rate: float
    pe_ratio: float
    adjust: str


@dataclass
class Snapshot:
    """Real-time or near-real-time quote snapshot."""
    symbol: str
    exchange: str
    name: str
    price: float
    pct_change: float
    volume: int
    turnover: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
    timestamp: datetime.datetime | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None


@dataclass
class Fundamentals:
    """Fundamental data for a stock."""
    symbol: str
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None
    circ_market_cap: float | None = None
    roe: float | None = None
    roa: float | None = None
    eps: float | None = None
    bps: float | None = None
    dividend_yield: float | None = None
    revenue: float | None = None
    net_profit: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue_yoy: float | None = None
    profit_yoy: float | None = None
    total_shares: int | None = None
    float_shares: int | None = None
    debt_ratio: float | None = None
    report_period: str | None = None  # e.g. "2025Q4"
    updated_at: datetime.datetime | None = None
    source: str | None = None


class CapitalFlow(TypedDict):
    """Capital flow data for a single day."""
    symbol: str
    date: datetime.date
    super_in: float
    big_in: float
    mid_in: float
    small_in: float
    main_in: float


class Plate(TypedDict):
    """Stock plate/sector membership."""
    symbol: str
    type: str       # "industry" or "concept"
    name: str       # e.g. "白酒", "消费升级"


class IncomeStatement(TypedDict):
    """Income statement data for a single reporting period."""
    symbol: str
    period: str           # e.g. "2025Q4"
    revenue: float
    cost_of_revenue: float
    gross_profit: float
    operating_income: float
    net_income: float
    eps_basic: float
    eps_diluted: float
    gross_margin: float
    operating_margin: float
    net_margin: float
    revenue_yoy: float
    profit_yoy: float


class CashFlowStatement(TypedDict):
    """Cash flow statement data for a single reporting period."""
    symbol: str
    period: str           # e.g. "2025Q4"
    operating_cf: float
    investing_cf: float
    financing_cf: float
    net_cf: float
    capex: float
    free_cf: float
    depreciation: float


class MacroPoint(TypedDict):
    """A single macro economic indicator data point."""
    indicator: str    # e.g. "fed_funds_rate", "cn_cpi_yoy"
    date: datetime.date
    value: float
    unit: str         # e.g. "%", "index", "千桶"
    source: str       # e.g. "fred", "akshare"
