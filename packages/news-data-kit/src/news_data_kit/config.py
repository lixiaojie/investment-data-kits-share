"""Portable configuration with packaged feeds and no workspace dependencies."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NewsKitConfig:
    data_root: Path = field(default_factory=lambda: Path(os.getenv(
        "NDK_DATA_ROOT", str(Path.home() / ".cache" / "news-data-kit-share"))))
    providers: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip() for x in os.getenv("NDK_PROVIDERS", "rss").split(",") if x.strip()))
    feeds_config: Path | None = field(default_factory=lambda: (
        Path(os.environ["NDK_FEEDS_CONFIG"]) if os.getenv("NDK_FEEDS_CONFIG") else None))
    retention_days: int = 30
    request_timeout: float = 10
    company_names: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self):
        self.data_root = Path(self.data_root).expanduser().resolve()
        self.providers = tuple(self.providers)
        if self.feeds_config is not None:
            self.feeds_config = Path(self.feeds_config).expanduser().resolve()
        if self.retention_days < 1 or self.request_timeout <= 0:
            raise ValueError("Retention and timeout must be positive")

    @property
    def db_path(self):
        return self.data_root / "news.db"

    @property
    def articles_dir(self):
        return self.data_root / "articles"

    @property
    def cache_dir(self):
        return self.data_root / "cache"

    def ensure_dirs(self):
        self.data_root.mkdir(parents=True, exist_ok=True)


_config = None


def init(**kwargs):
    global _config
    _config = NewsKitConfig(**kwargs)
    return _config


def get_config():
    return _config if _config is not None else init()


def reset():
    global _config
    _config = None
