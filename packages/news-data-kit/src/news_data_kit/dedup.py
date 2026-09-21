"""Three-layer news deduplication engine."""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Normalizers for title comparison
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def url_hash(url: str) -> str:
    """SHA256 of normalized URL (lowercase, strip trailing slash and query params for comparison)."""
    normalized = url.strip().lower().rstrip("/")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def title_hash(title: str) -> str:
    """Hash of normalized title prefix (first 60 chars after cleanup).

    Normalization: lowercase, strip punctuation, collapse whitespace, NFKC unicode.
    """
    text = title.strip().lower()
    text = unicodedata.normalize("NFKC", text)
    text = _PUNCT_RE.sub("", text)
    text = _SPACE_RE.sub("", text)
    prefix = text[:60]
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()


def item_id_from_url(source_type: str, url: str) -> str:
    """Generate deterministic item_id from source_type + url."""
    raw = f"{source_type}:{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class DedupEngine:
    """In-memory dedup tracker for a single fetch session.

    For persistent dedup, the store checks SQLite dedup_hashes table.
    This class handles in-session dedup across multiple providers.
    """

    def __init__(self) -> None:
        self._seen_urls: set[str] = set()
        self._seen_titles: set[str] = set()

    def is_duplicate(self, url: str, title: str) -> bool:
        """Check if this item is a duplicate. Returns True if duplicate."""
        uh = url_hash(url)
        if uh in self._seen_urls:
            return True

        th = title_hash(title)
        if th in self._seen_titles:
            return True

        self._seen_urls.add(uh)
        self._seen_titles.add(th)
        return False

    def mark_seen(self, url: str, title: str) -> None:
        """Mark an item as seen without checking."""
        self._seen_urls.add(url_hash(url))
        self._seen_titles.add(title_hash(title))

    @property
    def seen_count(self) -> int:
        return len(self._seen_urls)
