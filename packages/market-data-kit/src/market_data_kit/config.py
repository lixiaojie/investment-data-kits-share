"""Explicit, share-edition-only configuration. Initialization never fetches data."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    data_root: Path = field(default_factory=lambda: Path(os.getenv(
        "MDK_DATA_ROOT", str(Path.home() / ".cache" / "market-data-kit-share"))))
    providers: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip() for x in os.getenv("MDK_PROVIDERS", "yfinance,akshare,push2").split(",") if x.strip()))
    max_age_days: int = 3
    cache_ttl_seconds: int = 3600
    use_stubs: bool = field(default_factory=lambda: os.getenv("MDK_USE_STUBS", "") == "1")

    def __post_init__(self):
        self.data_root = Path(self.data_root).expanduser().resolve()
        self.providers = tuple(self.providers)
        if self.max_age_days < 0 or self.cache_ttl_seconds < 0:
            raise ValueError("Freshness limits must be nonnegative")


_config: Config | None = None


def init(**kwargs) -> Config:
    global _config
    from .providers.registry import FACTORIES, reset_registry
    cfg = Config(**kwargs)
    unknown = set(cfg.providers) - (set(FACTORIES) - {"stub"})
    if unknown:
        raise ValueError(f"Unknown providers: {sorted(unknown)}")
    reset_registry()
    _config = cfg
    return cfg


def get_config() -> Config:
    return _config if _config is not None else init()


def reset():
    global _config
    from .providers.registry import reset_registry
    reset_registry()
    _config = None
