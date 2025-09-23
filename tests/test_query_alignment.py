from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llmseo.audit import PageAudit, analyze_query_alignment
from llmseo.utils import flesch_reading_ease, word_stats


def make_page(body_text: str, headings: dict[str, list[str]]) -> PageAudit:
    stats = word_stats(body_text)
    reading = flesch_reading_ease(stats["word_count"], stats["sentence_count"], stats["syllables"])
    return PageAudit(
        url="https://example.com",
        status_code=200,
        title=headings.get("h1", ["Test Page"])[0] if headings.get("h1") else "Test Page",
        description=None,
        canonical=None,
        og_tags={},
        has_lang_attr=True,
        headings={
            "h1": headings.get("h1", []),
            "h2": headings.get("h2", []),
            "h3": headings.get("h3", []),
        },
        json_ld_types=[],
        has_faq_schema=False,
        text_stats=stats,
        reading_ease=reading,
        meta_robots=None,
        blocked_by_robots=False,
        semantic_tags_present=[],
    )


def test_query_alignment_flags_missing_terms():
    body = "Best CRM platforms provide automation for sales teams."
    headings = {
        "h1": ["Best CRM Platforms"],
        "h2": ["Features"],
        "h3": [],
    }
    page = make_page(body, headings)
    insights = analyze_query_alignment("best crm for startups", body, page)

    assert insights.terms_analyzed == ["best", "crm", "startups"]
    assert insights.present_terms == ["best", "crm"]
    assert "startups" in insights.missing_terms
    assert "startups" in insights.heading_terms_missing
    assert any("startups" in rec for rec in insights.recommendations)


def test_query_alignment_question_recommends_faq_section():
    body = "You should choose a CRM based on workflow and budget. This guide helps you choose the right CRM."
    headings = {
        "h1": ["CRM Buying Guide"],
        "h2": ["Key considerations"],
        "h3": [],
    }
    page = make_page(body, headings)
    insights = analyze_query_alignment("How do I choose a CRM?", body, page)

    assert insights.question_intent is True
    assert any("Q&A" in rec or "FAQ" in rec for rec in insights.recommendations)
    assert "choose" in insights.present_terms
    assert insights.phrase_present is False
