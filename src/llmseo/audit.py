from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

from .utils import normalize_url, extract_visible_text, word_stats, flesch_reading_ease, to_absolute, is_same_origin, clamp


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


@dataclass
class QueryInsights:
    query: str
    terms_analyzed: List[str]
    present_terms: List[str]
    missing_terms: List[str]
    heading_terms_present: List[str]
    heading_terms_missing: List[str]
    phrase_present: bool
    match_score: float
    question_intent: bool
    recommendations: List[str]


@dataclass
class SiteAudit:
    base_url: str
    robots_txt: Optional[str]
    sitemaps: List[str] = field(default_factory=list)
    llm_txt_url: Optional[str] = None
    llm_txt_found: bool = False
    llm_txt_body: Optional[str] = None
    page: Optional[PageAudit] = None
    score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    query_insights: Optional[QueryInsights] = None


UA = "llmseo-tool/0.1 (+https://example.com)"


STOPWORDS = {
    "the",
    "a",
    "an",
    "for",
    "to",
    "and",
    "or",
    "of",
    "in",
    "on",
    "at",
    "by",
    "from",
    "into",
    "is",
    "are",
    "was",
    "were",
    "be",
    "as",
    "that",
    "this",
    "these",
    "those",
    "it",
    "its",
    "your",
    "my",
    "our",
    "their",
    "about",
    "with",
    "without",
    "vs",
    "versus",
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "which",
    "can",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "if",
    "i",
    "we",
    "you",
    "they",
    "them",
    "us",
    "me",
}

SHORT_TERM_ALLOW = {"ai", "ml", "vr", "ar", "ui", "ux"}

QUESTION_PREFIXES = {
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "which",
    "can",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "is",
    "are",
}


def fetch(url: str, timeout: int = 15) -> Tuple[int, str, Dict[str, str]]:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    return resp.status_code, resp.text, resp.headers


def get_head(html: str) -> str:
    m = re.search(r"<head[\s\S]*?</head>", html, flags=re.I)
    return m.group(0) if m else ""


def get_attr(tag_html: str, attr: str) -> Optional[str]:
    # simple attribute extractor
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
    for m in re.finditer(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>", html, flags=re.I):
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


def normalize_query_terms(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    terms: List[str] = []
    for w in words:
        if (len(w) <= 2 and w not in SHORT_TERM_ALLOW) or w in STOPWORDS:
            continue
        if w not in terms:
            terms.append(w)
    return terms


def analyze_query_alignment(query: str, body_text: str, page: PageAudit) -> QueryInsights:
    query = query.strip()
    terms = normalize_query_terms(query)
    body_lower = body_text.lower()
    headings_text = " ".join(page.headings.get("h1", []) + page.headings.get("h2", []) + page.headings.get("h3", [])).lower()
    phrase_present = query.lower() in body_lower if query else False
    present_terms = [t for t in terms if re.search(fr"\b{re.escape(t)}\b", body_lower)]
    missing_terms = [t for t in terms if t not in present_terms]
    heading_terms_present = [t for t in terms if re.search(fr"\b{re.escape(t)}\b", headings_text)]
    heading_terms_missing = [t for t in terms if t not in heading_terms_present]
    question_marker = any(
        re.search(fr"\b{re.escape(word)}\b", headings_text) for word in QUESTION_PREFIXES
    )

    raw_lower = query.lower()
    question_intent = raw_lower.endswith("?") or any(raw_lower.startswith(prefix + " ") for prefix in QUESTION_PREFIXES)

    match_score = 0.0
    if terms:
        match_score = round((len(present_terms) / len(terms)) * 100, 1)
    elif phrase_present:
        match_score = 100.0

    recs: List[str] = []
    if not terms and not phrase_present:
        recs.append("Provide a more specific search phrase to analyze alignment.")
    if missing_terms:
        sample = ", ".join(missing_terms[:5])
        recs.append(f"Add copy that naturally includes: {sample}.")
    if heading_terms_missing:
        section_sample = ", ".join(heading_terms_missing[:3])
        recs.append(f"Introduce H2/H3 sections focusing on {section_sample}.")
    if query and not phrase_present:
        recs.append(f'Use the exact phrase "{query}" in a prominent section (intro, summary, or FAQ).')
    if question_intent and not re.search(r"\?", headings_text) and not question_marker:
        recs.append("Add a direct Q&A or FAQ entry that answers the question explicitly.")
    if match_score < 50 and (terms or phrase_present):
        recs.append("Create a dedicated section that fully answers the search intent with supporting details and examples.")

    if not recs and query:
        recs.append("Reinforce the query topic with a concise summary or FAQ answer to signal relevance to LLMs.")

    return QueryInsights(
        query=query,
        terms_analyzed=terms,
        present_terms=present_terms,
        missing_terms=missing_terms,
        heading_terms_present=heading_terms_present,
        heading_terms_missing=heading_terms_missing,
        phrase_present=phrase_present,
        match_score=match_score,
        question_intent=question_intent,
        recommendations=recs,
    )


def query_insights_to_dict(insights: Optional[QueryInsights]) -> Optional[Dict[str, object]]:
    if not insights:
        return None
    return {
        "query": insights.query,
        "terms_analyzed": insights.terms_analyzed,
        "present_terms": insights.present_terms,
        "missing_terms": insights.missing_terms,
        "heading_terms_present": insights.heading_terms_present,
        "heading_terms_missing": insights.heading_terms_missing,
        "phrase_present": insights.phrase_present,
        "match_score": insights.match_score,
        "question_intent": insights.question_intent,
        "recommendations": insights.recommendations,
    }


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
    # Very coarse: if path starts with any disallowed path
    from urllib.parse import urlparse

    p = urlparse(url)
    for d in disallow_paths:
        d = d.strip()
        if not d:
            continue
        if p.path.startswith(d):
            return True
    return False


def audit_url(url: str, target_query: Optional[str] = None) -> SiteAudit:
    url = normalize_url(url)
    target_query = (target_query or "").strip() or None
    site = SiteAudit(base_url=url, robots_txt=None)

    # Fetch main page
    status, html, headers = fetch(url)
    head = get_head(html)
    metas = extract_meta(head)
    title = extract_title(head)
    description = metas.get("name:description") or metas.get("prop:og:description")
    canonical = extract_canonical(head, url)
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
    reading_ease = flesch_reading_ease(stats["word_count"], stats["sentence_count"], stats["syllables"])
    meta_robots = metas.get("name:robots")
    semantic_tags_present = detect_semantic_tags(html)

    # robots.txt
    from urllib.parse import urlparse

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r_status, r_body, _ = fetch(robots_url)
        if 200 <= r_status < 300 and r_body:
            site.robots_txt = r_body
            r = parse_robots(r_body)
            site.sitemaps = r["sitemaps"]
            blocked = check_blocked(r["disallow"], url)
        else:
            blocked = False
    except Exception:
        blocked = False

    # llm.txt discovery
    llm_candidates = [
        f"{parsed.scheme}://{parsed.netloc}/.well-known/llm.txt",
        f"{parsed.scheme}://{parsed.netloc}/llm.txt",
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
            pass

    page = PageAudit(
        url=url,
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
    )
    site.page = page

    if target_query:
        site.query_insights = analyze_query_alignment(target_query, text, page)

    score_site(site)
    derive_recommendations(site)
    return site


def score_site(site: SiteAudit) -> None:
    page = site.page
    if not page:
        return

    # Weights (sum to 100)
    weights = {
        "indexability": 15.0,
        "metadata": 20.0,
        "structure": 20.0,
        "structured_data": 15.0,
        "content_depth": 15.0,
        "policy": 10.0,
        "sitemap": 5.0,
    }

    breakdown = {}

    # indexability
    idx = 1.0
    if page.blocked_by_robots:
        idx = 0.0
    if page.meta_robots and any(tok in page.meta_robots.lower() for tok in ["noindex", "nofollow"]):
        idx *= 0.3
    breakdown["indexability"] = weights["indexability"] * idx

    # metadata completeness: title, description, og tags, lang, canonical
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
    breakdown["metadata"] = weights["metadata"] * m_score

    # structure: h1 present, multiple h2/h3, semantic tags
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
    breakdown["structure"] = weights["structure"] * s_score

    # structured data: presence and helpful types
    sd_score = 0.0
    if site.page.json_ld_types:
        sd_score += 0.4
        # Boost for FAQ, Article, Product, Organization, WebSite
        target = {"FAQPage", "Article", "Product", "Organization", "WebSite", "HowTo"}
        if any(t in target for t in site.page.json_ld_types):
            sd_score += 0.4
    sd_score = clamp(sd_score, 0, 1)
    breakdown["structured_data"] = weights["structured_data"] * sd_score

    # content depth and readability
    c_score = 0.0
    wc = page.text_stats["word_count"]
    if wc >= 800:
        c_score += 0.5
    elif wc >= 400:
        c_score += 0.35
    elif wc >= 200:
        c_score += 0.2
    # readability ideal 50-70 (Flesch)
    re_score = 1.0 - (abs(page.reading_ease - 60) / 60)
    re_score = clamp(re_score, 0, 1)
    c_score = clamp(c_score + 0.3 * re_score, 0, 1)
    breakdown["content_depth"] = weights["content_depth"] * c_score

    # policy (llm.txt presence)
    p_score = 1.0 if site.llm_txt_found else 0.0
    breakdown["policy"] = weights["policy"] * p_score

    # sitemap presence in robots
    sm_score = 1.0 if site.sitemaps else 0.0
    breakdown["sitemap"] = weights["sitemap"] * sm_score

    total = sum(breakdown.values())
    site.score = round(total, 1)
    site.breakdown = {k: round(v, 1) for k, v in breakdown.items()}


def derive_recommendations(site: SiteAudit) -> None:
    recs: List[str] = []
    p = site.page
    if not p:
        site.recommendations = ["Failed to fetch the page."]
        return

    if p.blocked_by_robots:
        recs.append("Allow the page in robots.txt (avoid disallowing this path).")
    if p.meta_robots and any(tok in p.meta_robots.lower() for tok in ["noindex", "nofollow"]):
        recs.append("Remove 'noindex'/'nofollow' meta robots for LLM discoverability.")
    if not p.title or not (10 <= len((p.title or '').strip()) <= 65):
        recs.append("Add a concise, descriptive <title> (10–65 chars).")
    if not p.description or not (50 <= len((p.description or '').strip()) <= 160):
        recs.append("Add a meta description (50–160 chars) summarizing the page.")
    if not p.canonical:
        recs.append("Add a canonical <link> to prevent duplication.")
    if not p.has_lang_attr:
        recs.append("Set the <html lang=""...""> attribute for language clarity.")
    if not p.headings["h1"]:
        recs.append("Include a single, clear H1 headline.")
    if len(p.headings["h2"]) < 2:
        recs.append("Structure content with multiple H2 sections.")
    if len(p.headings["h3"]) < 2:
        recs.append("Use H3 subsections to organize details.")
    if not p.semantic_tags_present:
        recs.append("Use semantic HTML (<article>, <section>, <main>, etc.).")
    if not p.json_ld_types:
        recs.append("Add JSON-LD structured data (WebSite/Organization/Article/FAQ).")
    elif not p.has_faq_schema:
        recs.append("Add FAQPage JSON-LD for common questions and answers.")
    if p.text_stats["word_count"] < 400:
        recs.append("Increase content depth to 400–800+ words of unique text.")
    if not site.sitemaps:
        recs.append("Expose a Sitemap in robots.txt for better discovery.")
    if not site.llm_txt_found:
        recs.append("Publish /.well-known/llm.txt with LLM crawl/citation policy.")

    site.recommendations = recs

