from __future__ import annotations

import json
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from .utils import (
    clamp,
    extract_links,
    extract_visible_text,
    flesch_reading_ease,
    is_same_origin,
    normalize_url,
    to_absolute,
    word_stats,
)


@dataclass
class KeywordInsight:
    term: str
    score: float
    frequency: int
    in_title: bool
    in_headings: bool
    in_description: bool


@dataclass
class KeywordSummary:
    term: str
    score: float
    pages: int


@dataclass
class PageAudit:
    url: str
    status_code: int
    title: Optional[str]
    description: Optional[str]
    canonical: Optional[str]
    og_tags: Dict[str, str]
    has_lang_attr: bool
    headings: Dict[str, List[str]]
    json_ld_types: List[str]
    has_faq_schema: bool
    text_stats: Dict[str, float]
    reading_ease: float
    meta_robots: Optional[str]
    blocked_by_robots: bool
    semantic_tags_present: List[str]
    keywords: List[KeywordInsight] = field(default_factory=list)
    score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class SiteAudit:
    base_url: str
    robots_txt: Optional[str]
    sitemaps: List[str] = field(default_factory=list)
    llm_txt_url: Optional[str] = None
    llm_txt_found: bool = False
    llm_txt_body: Optional[str] = None
    page: Optional[PageAudit] = None
    pages: List[PageAudit] = field(default_factory=list)
    score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    keywords: List[KeywordSummary] = field(default_factory=list)


UA = "llmseo-tool/0.1 (+https://example.com)"
WEIGHTS = {
    "indexability": 15.0,
    "metadata": 20.0,
    "structure": 20.0,
    "structured_data": 15.0,
    "content_depth": 15.0,
    "policy": 10.0,
    "sitemap": 5.0,
}
NON_HTML_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".pdf",
    ".zip",
    ".mp4",
    ".mp3",
    ".mov",
    ".avi",
}
MAX_LINKS_PER_PAGE = 50
STOPWORDS = {
    "the",
    "that",
    "with",
    "this",
    "from",
    "have",
    "your",
    "about",
    "their",
    "there",
    "will",
    "would",
    "could",
    "should",
    "into",
    "while",
    "where",
    "these",
    "those",
    "what",
    "when",
    "which",
    "were",
    "been",
    "them",
    "they",
    "also",
    "than",
    "then",
    "over",
    "such",
    "only",
    "some",
    "more",
    "most",
    "many",
    "each",
    "other",
    "into",
    "your",
    "ours",
    "ourselves",
    "yours",
    "itself",
    "it",
    "here",
    "make",
    "made",
    "just",
    "very",
    "much",
    "like",
    "have",
    "been",
    "does",
    "doesn",
    "again",
    "even",
    "through",
    "within",
    "across",
    "because",
    "after",
    "before",
    "under",
    "above",
    "upon",
    "once",
    "every",
    "being",
    "same",
    "such",
    "another",
    "including",
    "include",
    "between",
    "might",
    "shall",
}


def fetch(url: str, timeout: int = 15) -> Tuple[int, str, Dict[str, str]]:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    return resp.status_code, resp.text, resp.headers


def get_head(html: str) -> str:
    m = re.search(r"<head[\s\S]*?</head>", html, flags=re.I)
    return m.group(0) if m else ""


def get_attr(tag_html: str, attr: str) -> Optional[str]:
    m = re.search(fr"{attr}=[\"']([^\"']+)[\"']", tag_html, flags=re.I)
    return m.group(1) if m else None


def extract_meta(head_html: str) -> Dict[str, str]:
    metas = {}
    for m in re.finditer(r"<meta[^>]+>", head_html, flags=re.I):
        tag = m.group(0)
        name = get_attr(tag, "name")
        prop = get_attr(tag, "property")
        content = get_attr(tag, "content") or ""
        if name:
            metas[f"name:{name.lower()}"] = content
        if prop:
            metas[f"prop:{prop.lower()}"] = content
    return metas


def extract_title(head_html: str) -> Optional[str]:
    m = re.search(r"<title>([\s\S]*?)</title>", head_html, flags=re.I)
    return m.group(1).strip() if m else None


def extract_canonical(head_html: str, base_url: str) -> Optional[str]:
    for m in re.finditer(r"<link[^>]+>", head_html, flags=re.I):
        tag = m.group(0)
        rel = (get_attr(tag, "rel") or "").lower()
        if "canonical" in rel:
            href = get_attr(tag, "href")
            if href:
                return to_absolute(base_url, href)
    return None


def extract_json_ld_types(html: str) -> Tuple[List[str], bool]:
    types: List[str] = []
    has_faq = False
    for m in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>", html, flags=re.I
    ):
        body = m.group(1).strip()
        try:
            data = json.loads(body)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            t = it.get("@type")
            if isinstance(t, list):
                types.extend(map(str, t))
            elif isinstance(t, str):
                types.append(t)
            if (isinstance(t, str) and t.lower() == "faqpage") or (
                isinstance(t, list) and any(str(x).lower() == "faqpage" for x in t)
            ):
                has_faq = True
    return list(dict.fromkeys(types)), has_faq


def detect_semantic_tags(html: str) -> List[str]:
    tags = ["article", "section", "nav", "aside", "main", "header", "footer"]
    present = []
    for t in tags:
        if re.search(fr"<\s*{t}(\s|>)", html, flags=re.I):
            present.append(t)
    return present


def tokenize_for_keywords(text: Optional[str]) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    return [t for t in tokens if len(t) > 3 and t not in STOPWORDS]


def extract_keywords(
    body_text: str,
    title: Optional[str],
    headings: Dict[str, List[str]],
    description: Optional[str],
    max_keywords: int = 10,
) -> List[KeywordInsight]:
    tokens = tokenize_for_keywords(body_text)
    if not tokens:
        return []

    frequencies = Counter(tokens)
    max_freq = max(frequencies.values()) if frequencies else 0

    title_tokens = set(tokenize_for_keywords(title))
    desc_tokens = set(tokenize_for_keywords(description))

    h1_tokens: Set[str] = set()
    h2_tokens: Set[str] = set()
    h3_tokens: Set[str] = set()
    for h in headings.get("h1", []):
        h1_tokens.update(tokenize_for_keywords(h))
    for h in headings.get("h2", []):
        h2_tokens.update(tokenize_for_keywords(h))
    for h in headings.get("h3", []):
        h3_tokens.update(tokenize_for_keywords(h))

    insights: List[KeywordInsight] = []
    for term, freq in frequencies.items():
        base = (freq / max_freq) if max_freq else 0.0
        score = base * 60.0
        in_title = term in title_tokens
        in_h1 = term in h1_tokens
        in_h2 = term in h2_tokens
        in_h3 = term in h3_tokens
        in_description = term in desc_tokens

        if in_title:
            score += 25.0
        if in_h1:
            score += 15.0
        if in_h2:
            score += 10.0
        if in_h3:
            score += 5.0
        if in_description:
            score += 5.0

        insights.append(
            KeywordInsight(
                term=term,
                score=round(clamp(score, 0.0, 100.0), 1),
                frequency=freq,
                in_title=in_title,
                in_headings=in_h1 or in_h2 or in_h3,
                in_description=in_description,
            )
        )

    insights.sort(key=lambda k: (k.score, k.frequency), reverse=True)
    return insights[:max_keywords]


def parse_robots(robots_txt: str) -> Dict[str, List[str]]:
    sitemaps = []
    disallow = []
    allow = []
    for line in robots_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("sitemap:"):
            sitemaps.append(line.split(":", 1)[1].strip())
        elif line.lower().startswith("disallow:"):
            disallow.append(line.split(":", 1)[1].strip())
        elif line.lower().startswith("allow:"):
            allow.append(line.split(":", 1)[1].strip())
    return {"sitemaps": sitemaps, "disallow": disallow, "allow": allow}


def check_blocked(disallow_paths: List[str], url: str) -> bool:
    parsed = urlparse(url)
    for d in disallow_paths:
        d = d.strip()
        if not d:
            continue
        if parsed.path.startswith(d):
            return True
    return False


def _score_components(page: PageAudit, site: SiteAudit) -> Dict[str, float]:
    components: Dict[str, float] = {}

    idx = 1.0
    if page.blocked_by_robots:
        idx = 0.0
    if page.meta_robots and any(tok in page.meta_robots.lower() for tok in ["noindex", "nofollow"]):
        idx *= 0.3
    components["indexability"] = WEIGHTS["indexability"] * idx

    m_score = 0.0
    if page.title and 10 <= len(page.title.strip()) <= 65:
        m_score += 0.35
    elif page.title:
        m_score += 0.2
    if page.description and 50 <= len(page.description.strip()) <= 160:
        m_score += 0.25
    elif page.description:
        m_score += 0.15
    if page.og_tags.get("og:title") or page.og_tags.get("title"):
        m_score += 0.15
    if page.og_tags.get("og:description") or page.og_tags.get("description"):
        m_score += 0.1
    if page.canonical:
        m_score += 0.1
    if page.has_lang_attr:
        m_score += 0.05
    m_score = clamp(m_score, 0, 1)
    components["metadata"] = WEIGHTS["metadata"] * m_score

    s_score = 0.0
    if page.headings["h1"]:
        s_score += 0.45
    if len(page.headings["h2"]) >= 2:
        s_score += 0.25
    if len(page.headings["h3"]) >= 2:
        s_score += 0.15
    if page.semantic_tags_present:
        s_score += 0.15
    s_score = clamp(s_score, 0, 1)
    components["structure"] = WEIGHTS["structure"] * s_score

    sd_score = 0.0
    if page.json_ld_types:
        sd_score += 0.4
        target = {"FAQPage", "Article", "Product", "Organization", "WebSite", "HowTo"}
        if any(t in target for t in page.json_ld_types):
            sd_score += 0.4
    sd_score = clamp(sd_score, 0, 1)
    components["structured_data"] = WEIGHTS["structured_data"] * sd_score

    c_score = 0.0
    wc = page.text_stats.get("word_count", 0)
    if wc >= 800:
        c_score += 0.5
    elif wc >= 400:
        c_score += 0.35
    elif wc >= 200:
        c_score += 0.2
    re_score = 1.0 - (abs(page.reading_ease - 60) / 60)
    re_score = clamp(re_score, 0, 1)
    c_score = clamp(c_score + 0.3 * re_score, 0, 1)
    components["content_depth"] = WEIGHTS["content_depth"] * c_score

    p_score = 1.0 if site.llm_txt_found else 0.0
    components["policy"] = WEIGHTS["policy"] * p_score

    sm_score = 1.0 if site.sitemaps else 0.0
    components["sitemap"] = WEIGHTS["sitemap"] * sm_score

    return components


def score_site(site: SiteAudit) -> None:
    if not site.pages:
        site.score = 0.0
        site.breakdown = {k: 0.0 for k in WEIGHTS}
        return

    totals = {k: 0.0 for k in WEIGHTS}
    aggregated_score = 0.0
    for page in site.pages:
        components = _score_components(page, site)
        page_score = sum(components.values())
        page.score = round(page_score, 1)
        page.breakdown = {k: round(v, 1) for k, v in components.items()}
        aggregated_score += page_score
        for k, v in components.items():
            totals[k] += v

    count = len(site.pages)
    site.score = round(aggregated_score / count, 1)
    site.breakdown = {k: round((totals[k] / count), 1) for k in totals}
    site.page = site.pages[0]


def _page_recommendations(page: PageAudit) -> List[str]:
    recs: List[str] = []
    if page.blocked_by_robots:
        recs.append("Allow the page in robots.txt (avoid disallowing this path).")
    if page.meta_robots and any(tok in page.meta_robots.lower() for tok in ["noindex", "nofollow"]):
        recs.append("Remove 'noindex'/'nofollow' meta robots for LLM discoverability.")
    if not page.title or not (10 <= len((page.title or '').strip()) <= 65):
        recs.append("Add a concise, descriptive <title> (10–65 chars).")
    if not page.description or not (50 <= len((page.description or '').strip()) <= 160):
        recs.append("Add a meta description (50–160 chars) summarizing the page.")
    if not page.canonical:
        recs.append("Add a canonical <link> to prevent duplication.")
    if not page.has_lang_attr:
        recs.append("Set the <html lang=\"...\"> attribute for language clarity.")
    if not page.headings["h1"]:
        recs.append("Include a single, clear H1 headline.")
    if len(page.headings["h2"]) < 2:
        recs.append("Structure content with multiple H2 sections.")
    if len(page.headings["h3"]) < 2:
        recs.append("Use H3 subsections to organize details.")
    if not page.semantic_tags_present:
        recs.append("Use semantic HTML (<article>, <section>, <main>, etc.).")
    if not page.json_ld_types:
        recs.append("Add JSON-LD structured data (WebSite/Organization/Article/FAQ).")
    elif not page.has_faq_schema:
        recs.append("Add FAQPage JSON-LD for common questions and answers.")
    if page.text_stats.get("word_count", 0) < 400:
        recs.append("Increase content depth to 400–800+ words of unique text.")
    return recs


def derive_recommendations(site: SiteAudit) -> None:
    if not site.pages:
        site.recommendations = ["Failed to fetch any pages."]
        return

    seen: Set[str] = set()
    combined: List[str] = []
    multi_page = len(site.pages) > 1
    for page in site.pages:
        page.recommendations = _page_recommendations(page)
        for rec in page.recommendations:
            message = rec if not multi_page else f"[{page.url}] {rec}"
            if message in seen:
                continue
            seen.add(message)
            combined.append(message)

    if not site.sitemaps:
        combined.append("Expose a Sitemap in robots.txt for better discovery.")
    if not site.llm_txt_found:
        combined.append("Publish /.well-known/llm.txt with LLM crawl/citation policy.")

    site.recommendations = combined


def aggregate_keywords(site: SiteAudit, max_terms: int = 12) -> List[KeywordSummary]:
    buckets: Dict[str, List[float]] = {}
    for page in site.pages:
        for kw in page.keywords:
            buckets.setdefault(kw.term, []).append(kw.score)

    summaries: List[KeywordSummary] = []
    for term, scores in buckets.items():
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        summaries.append(KeywordSummary(term=term, score=round(avg, 1), pages=len(scores)))

    summaries.sort(key=lambda s: (s.score, s.pages), reverse=True)
    return summaries[:max_terms]


def _should_follow(link: str) -> bool:
    parsed = urlparse(link)
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.lower()
    return not any(path.endswith(ext) for ext in NON_HTML_EXTENSIONS)


def audit_url(url: str, max_pages: int = 1) -> SiteAudit:
    url = normalize_url(url)
    try:
        max_pages = int(max_pages)
    except (TypeError, ValueError):
        max_pages = 1
    max_pages = max(1, max_pages)

    site = SiteAudit(base_url=url, robots_txt=None)

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    disallow_paths: List[str] = []
    robots_url = f"{origin}/robots.txt"
    try:
        r_status, r_body, _ = fetch(robots_url)
        if 200 <= r_status < 300 and r_body:
            site.robots_txt = r_body
            robots_data = parse_robots(r_body)
            site.sitemaps = robots_data["sitemaps"]
            disallow_paths = robots_data["disallow"]
    except Exception:
        pass

    llm_candidates = [
        f"{origin}/.well-known/llm.txt",
        f"{origin}/llm.txt",
    ]
    for cand in llm_candidates:
        try:
            c_status, c_body, _ = fetch(cand)
            if 200 <= c_status < 300 and c_body:
                site.llm_txt_found = True
                site.llm_txt_url = cand
                site.llm_txt_body = c_body
                break
        except Exception:
            continue

    queue: Deque[str] = deque([url])
    visited: Set[str] = set()

    while queue and len(site.pages) < max_pages:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            status, html, _ = fetch(current)
        except Exception:
            status, html = 0, ""

        head = get_head(html)
        metas = extract_meta(head)
        title = extract_title(head)
        description = metas.get("name:description") or metas.get("prop:og:description")
        canonical = extract_canonical(head, current)
        og = {k[5:]: v for k, v in metas.items() if k.startswith("prop:og:")}
        has_lang_attr = bool(re.search(r"<html[^>]+lang=", html, flags=re.I))
        headings = {
            "h1": re.findall(r"<h1[^>]*>([\s\S]*?)</h1>", html, flags=re.I),
            "h2": re.findall(r"<h2[^>]*>([\s\S]*?)</h2>", html, flags=re.I),
            "h3": re.findall(r"<h3[^>]*>([\s\S]*?)</h3>", html, flags=re.I),
        }
        json_ld_types, has_faq_schema = extract_json_ld_types(html)
        text = extract_visible_text(html)
        stats = word_stats(text)
        reading_ease = flesch_reading_ease(
            int(stats.get("word_count", 0)),
            int(stats.get("sentence_count", 0)),
            int(stats.get("syllables", 0)),
        )
        meta_robots = metas.get("name:robots")
        semantic_tags_present = detect_semantic_tags(html)
        blocked = check_blocked(disallow_paths, current) if disallow_paths else False
        keywords = extract_keywords(
            text,
            title=title,
            headings=headings,
            description=description,
        )

        page = PageAudit(
            url=current,
            status_code=status,
            title=title,
            description=description,
            canonical=canonical,
            og_tags=og,
            has_lang_attr=has_lang_attr,
            headings=headings,
            json_ld_types=json_ld_types,
            has_faq_schema=has_faq_schema,
            text_stats=stats,
            reading_ease=reading_ease,
            meta_robots=meta_robots,
            blocked_by_robots=blocked,
            semantic_tags_present=semantic_tags_present,
            keywords=keywords,
        )
        site.pages.append(page)

        if html and len(site.pages) < max_pages:
            for link in extract_links(current, html, limit=MAX_LINKS_PER_PAGE):
                clean = link.split("#", 1)[0]
                if clean in visited:
                    continue
                if not is_same_origin(url, clean):
                    continue
                if not _should_follow(clean):
                    continue
                if clean == current:
                    continue
                if clean in queue:
                    continue
                queue.append(clean)

    score_site(site)
    site.keywords = aggregate_keywords(site)
    derive_recommendations(site)
    return site
