from __future__ import annotations

import re
from typing import List
from urllib.parse import urlparse, urljoin, urlunparse


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    scheme = (parsed.scheme or "").lower()
    netloc = parsed.netloc
    path = parsed.path
    query = parsed.query

    if not netloc:
        if scheme not in {"http", "https"}:
            scheme = "https"
        reparsed = urlparse(f"//{cleaned}", scheme=scheme)
        if reparsed.netloc:
            netloc = reparsed.netloc
            path = reparsed.path
            query = reparsed.query or query
    else:
        scheme = scheme or "https"

    if not netloc and path and not path.startswith("/"):
        netloc = path
        path = ""

    if not netloc:
        raise ValueError(f"Cannot determine host for URL: {url!r}")

    if not path:
        path = "/"
    elif not path.startswith("/"):
        path = f"/{path}"

    return urlunparse((scheme, netloc, path, "", query, ""))


def is_same_origin(base: str, other: str) -> bool:
    b = urlparse(base)
    o = urlparse(other)
    return (b.scheme, b.netloc) == (o.scheme, o.netloc)


def to_absolute(base: str, maybe_rel: str) -> str:
    return urljoin(base, maybe_rel)


def extract_visible_text(html: str) -> str:
    # Lightweight text extraction sans external libs
    # Remove script/style
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    # Remove comments
    html = re.sub(r"<!--([\s\S]*?)-->", " ", html)
    # Replace block tags with newlines for better splitting
    html = re.sub(r"</?(?:p|div|section|article|li|br|h[1-6]|tr|td|th|ul|ol|nav|footer|header)[^>]*>", "\n", html, flags=re.I)
    # Strip all other tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def word_stats(text: str) -> dict:
    words = re.findall(r"[A-Za-z']+", text)
    wc = len(words)
    uniq = len(set(w.lower() for w in words))
    sentences = re.split(r"[.!?]+\s+", text)
    sentences = [s for s in sentences if s.strip()]
    sc = max(1, len(sentences))
    syllables = sum(estimate_syllables(w) for w in words)
    return {
        "word_count": wc,
        "unique_words": uniq,
        "sentence_count": sc,
        "syllables": syllables,
        "avg_sentence_len": wc / sc if sc else 0,
    }


def estimate_syllables(word: str) -> int:
    word = word.lower()
    # Simple heuristic for syllables
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def flesch_reading_ease(words: int, sentences: int, syllables: int) -> float:
    if words == 0 or sentences == 0:
        return 0.0
    return 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)


def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def extract_links(base_url: str, html: str, limit: int = 50) -> List[str]:
    """Return up to ``limit`` absolute URLs discovered in anchor tags."""
    links: List[str] = []
    seen = set()
    for match in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"']", html, flags=re.I):
        href = match.group(1).strip()
        if not href or href.startswith("#"):
            continue
        lower = href.lower()
        if lower.startswith("javascript:") or lower.startswith("mailto:"):
            continue
        absolute = to_absolute(base_url, href)
        if not absolute:
            continue
        absolute = absolute.split("#", 1)[0]
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
        if len(links) >= limit:
            break
    return links
