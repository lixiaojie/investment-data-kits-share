"""Base provider protocol and exceptions."""
from __future__ import annotations

import datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd

__all__ = [
    "BaseProvider",
    "DataNotFoundError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
]


class ProviderError(Exception):
    """Base exception for provider errors."""


class DataNotFoundError(ProviderError):
    """Raised when requested data is not available from this provider."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider rejects a request due to rate limiting.

    Distinct from DataNotFoundError: we don't know whether data exists,
    only that we were blocked. Registry treats this as a transient failure
    that counts toward circuit breaker AND forces fallback to the next provider
    in the chain. Consumers should NOT treat this as "no data" — caching a
    None result here would poison cache entries.
    """

    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    """All providers for a (data_type, market) are temporarily unavailable.

    Raised by fetch_with_fallback when every provider in the chain either
    errored (connection reset, timeout, etc.) or was skipped by circuit breaker.
    Consumers should catch this to show "data temporarily unavailable" and
    avoid retrying immediately.

    Attributes:
        retry_after: Seconds until the earliest circuit breaker may re-open.
            0 means unknown or no CB info (consumer should use own backoff).
    """

    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class BaseProvider(Protocol):
    """Protocol that all data providers must implement.

    Providers override only the methods they support.
    Unsupported methods should raise NotImplementedError.
    """
    name: str

    def fetch_klines(self, symbol: str, days: int,
                     end_date: datetime.date | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_klines")

    def fetch_snapshot(self, symbols: list[str]) -> list[dict]:
        raise NotImplementedError(f"{self.name} does not support fetch_snapshot")

    def fetch_fundamentals(self, symbol: str) -> dict:
        raise NotImplementedError(f"{self.name} does not support fetch_fundamentals")

    def fetch_capital_flow(self, symbol: str, days: int = 5) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_capital_flow")

    def fetch_plates(self, symbol: str) -> list[dict]:
        raise NotImplementedError(f"{self.name} does not support fetch_plates")

    def fetch_income_statement(self, symbol: str) -> list[dict]:
        raise NotImplementedError(f"{self.name} does not support fetch_income_statement")

    def fetch_cash_flow_statement(self, symbol: str) -> list[dict]:
        raise NotImplementedError(f"{self.name} does not support fetch_cash_flow_statement")

    def healthcheck(self) -> bool:
        return True
