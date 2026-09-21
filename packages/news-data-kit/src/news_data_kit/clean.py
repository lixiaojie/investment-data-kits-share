"""News text cleaning utilities."""

from __future__ import annotations

import re

# Advertorial filter patterns (Chinese fund promotional content)
_AD_PATTERNS_ZH = [
    re.compile(r"基金\s*(代码|申购|定投|净值|经理)", re.IGNORECASE),
    re.compile(r"(认购|申购|赎回)\s*(费率|手续费)"),
    re.compile(r"(风险等级|投资有风险|过往业绩)"),
    re.compile(r"本(基金|产品)\s*(由|管理人)"),
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)


def strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not text:
        return ""
    # Unwrap CDATA sections
    text = _CDATA_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncate text to max_chars, breaking at sentence boundary if possible."""
    if not text or len(text) <= max_chars:
        return text
    # Try to break at last sentence boundary within limit
    truncated = text[:max_chars]
    for sep in ("。", ".", "！", "!", "？", "?", "；", ";"):
        last = truncated.rfind(sep)
        if last > max_chars * 0.6:
            return truncated[: last + 1]
    return truncated + "…"


def is_advertorial(title: str, summary: str = "") -> bool:
    """Check if content is likely a fund/product advertisement (Chinese)."""
    text = f"{title} {summary}"
    return any(pat.search(text) for pat in _AD_PATTERNS_ZH)


def clean_item(title: str, summary: str = "", full_text: str | None = None) -> tuple[str, str, str | None]:
    """Clean a news item's text fields.

    Returns (cleaned_title, cleaned_summary, cleaned_full_text).
    """
    title = strip_html(title).strip()
    summary = truncate(strip_html(summary))
    if full_text:
        full_text = strip_html(full_text)
    return title, summary, full_text
