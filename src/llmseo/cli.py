from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_url
from .llm_txt import generate_llm_txt


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="llm-seo",
        description="Audit a website for LLM discoverability, generate llm.txt, and recommendations.",
    )
    parser.add_argument("url", help="Website/page URL to audit (e.g., https://example.com)")
    parser.add_argument("--save-llm-txt", action="store_true", help="Write generated llm.txt to output directory")
    parser.add_argument("--out-dir", default=".", help="Directory to write outputs (default: current directory)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output JSON report to stdout")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Sample up to N internal pages and average results (default: 1)",
    )
    args = parser.parse_args(argv)

    site = audit_url(args.url, max_pages=args.max_pages)

    # Generate llm.txt draft
    llm_txt = generate_llm_txt(site.base_url, sitemaps=site.sitemaps)

    # Save if requested
    if args.save_llm_txt:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "llm.txt").write_text(llm_txt, encoding="utf-8")

    if args.as_json:
        pages_payload = [
            {
                "url": p.url,
                "status_code": p.status_code,
                "score": p.score,
                "breakdown": p.breakdown,
                "title": p.title,
                "description": p.description,
                "canonical": p.canonical,
                "og": p.og_tags,
                "json_ld_types": p.json_ld_types,
                "reading_ease": p.reading_ease,
                "word_count": p.text_stats.get("word_count"),
                "has_faq_schema": p.has_faq_schema,
                "blocked_by_robots": p.blocked_by_robots,
                "meta_robots": p.meta_robots,
                "recommendations": p.recommendations,
            }
            for p in site.pages
        ]
        print(
            json.dumps(
                {
                    "score": site.score,
                    "breakdown": site.breakdown,
                    "recommendations": site.recommendations,
                    "sampled_pages": len(site.pages),
                    "pages": pages_payload,
                    "page": {
                        "url": site.page.url if site.page else None,
                        "status_code": site.page.status_code if site.page else None,
                        "title": site.page.title if site.page else None,
                        "description": site.page.description if site.page else None,
                        "canonical": site.page.canonical if site.page else None,
                        "og": site.page.og_tags if site.page else None,
                        "json_ld_types": site.page.json_ld_types if site.page else None,
                        "reading_ease": site.page.reading_ease if site.page else None,
                        "word_count": site.page.text_stats.get("word_count") if site.page else None,
                        "has_faq_schema": site.page.has_faq_schema if site.page else None,
                        "blocked_by_robots": site.page.blocked_by_robots if site.page else None,
                    },
                    "llm_txt_found": site.llm_txt_found,
                    "llm_txt_url": site.llm_txt_url,
                    "sitemaps": site.sitemaps,
                    "llm_txt_draft": llm_txt,
                },
                indent=2,
            )
        )
        return 0

    # Human-readable output
    total_pages = len(site.pages)
    print(f"LLM Discoverability Score (avg across {total_pages} page(s)): {site.score}/100")
    if site.breakdown:
        print("Breakdown (average contributions):")
        for k, v in site.breakdown.items():
            print(f"  - {k}: {v}")

    if total_pages:
        print(f"\nPages audited: {total_pages}")
        for idx, p in enumerate(site.pages, start=1):
            print(f"\nPage {idx}: {p.url}")
            print(f"  Score: {p.score}/100")
            print(f"  Status: {p.status_code}")
            print(f"  Title: {p.title or '(missing)'}")
            print(f"  Description: {p.description or '(missing)'}")
            print(f"  Canonical: {p.canonical or '(missing)'}")
            print(f"  JSON-LD types: {', '.join(p.json_ld_types) or '(none)'}")
            print(f"  Word count: {p.text_stats.get('word_count', 0)}")
            print(f"  Flesch reading ease: {p.reading_ease:.1f}")
            print(f"  Has FAQ schema: {'yes' if p.has_faq_schema else 'no'}")
            print(f"  Robots blocked: {'yes' if p.blocked_by_robots else 'no'}")

    print(f"\nSitemap(s): {', '.join(site.sitemaps) if site.sitemaps else '(none found)'}")
    print(f"LLM policy present: {'yes' if site.llm_txt_found else 'no'}")

    if site.recommendations:
        print("\nRecommendations:")
        for r in site.recommendations:
            print(f"  - {r}")

    print("\nGenerated llm.txt (preview):\n")
    print(llm_txt)

    if args.save_llm_txt:
        print("Saved llm.txt to:", str(Path(args.out_dir) / "llm.txt"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
