from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse


LLM_TXT_TEMPLATE = """# llm.txt — Guidance for LLM crawlers and trainers
# Learn more: https://www.llmtext.org/ (example placeholder link)

User-agent: *
# Options: allow, disallow, no-train, no-derive, cite-required
Policy: allow

# Crawl policy
Crawl-Delay: 2

# Sitemaps
{sitemaps}

# Canonical host (optional)
Host: {host}

# Content usage and attribution
License: {license_url}
Attribution: required
Attribution-Format: link
Contact: {contact}

# Preferred citation pages (optional)
Preferred-Sources: {preferred_sources}

# API endpoints (optional)
APIs: {apis}

# Notes
Note: This file expresses publisher preferences for LLMs. It complements robots.txt.
"""


def generate_llm_txt(
    site_url: str,
    sitemaps: Optional[List[str]] = None,
    contact: str = "webmaster@domain",
    license_url: str = "https://creativecommons.org/licenses/by/4.0/",
    preferred_sources: Optional[List[str]] = None,
    apis: Optional[List[str]] = None,
) -> str:
    parsed = urlparse(site_url)
    host = parsed.netloc
    sitemaps_block = "\n".join(f"Sitemap: {s}" for s in (sitemaps or [])) or "# (add sitemap URLs here)"
    preferred_block = ", ".join(preferred_sources or []) or "# add important URLs"
    apis_block = ", ".join(apis or []) or "# add API endpoints if relevant"
    return LLM_TXT_TEMPLATE.format(
        sitemaps=sitemaps_block,
        host=host,
        license_url=license_url,
        contact=contact,
        preferred_sources=preferred_block,
        apis=apis_block,
    )

