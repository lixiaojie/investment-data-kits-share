"""Base protocol for news providers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..types import NewsItem


@runtime_checkable
class BaseNewsProvider(Protocol):
    """Interface that all news providers must implement."""

    name: str

    def fetch(
        self,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
        keywords: list[str] | None = None,
        since: datetime | None = None,
        max_items: int = 50,
    ) -> list[NewsItem]:
        """Fetch news items from this provider.

        Args:
            markets: Filter by market codes (HK, CN, US). None = all.
            symbols: Filter by stock symbols. None = all.
            keywords: Search keywords. None = no filter.
            since: Only fetch items after this time. None = provider default.
            max_items: Maximum items to return.

        Returns:
            List of NewsItem (before tagging/dedup — raw from provider).

        Raises:
            NotImplementedError: Provider doesn't support this combination.
        """
        ...

    def healthcheck(self) -> bool:
        """Check if the provider is available. Returns True if healthy."""
        ...
