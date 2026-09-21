"""TTL file cache for news provider responses."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileCache:
    """Simple JSON file cache with TTL."""

    def __init__(self, cache_dir: Path, default_ttl: int = 1800):
        self._dir = cache_dir
        self._default_ttl = default_ttl
        self._dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, ttl: int | None = None) -> Any | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("_ts", 0) < (ttl or self._default_ttl):
                return data.get("value")
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any) -> None:
        path = self._dir / f"{key}.json"
        try:
            path.write_text(
                json.dumps({"_ts": time.time(), "value": value}, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Cache write failed for %s: %s", key, exc)

    def clear(self) -> int:
        """Remove all cached files. Returns count removed."""
        count = 0
        for f in self._dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        return count
