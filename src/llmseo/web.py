from __future__ import annotations

import argparse
import json
from textwrap import dedent
from typing import Any, Dict

from flask import Flask, jsonify, request, Response

from .audit import audit_url
from .llm_txt import generate_llm_txt


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        html = dedent(
            """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1" />
              <title>LLM Discoverability Audit</title>
              <style>
                :root { --bg:#0c0d0f; --fg:#e8e8ea; --muted:#a7a7ad; --card:#15171a; --acc:#4f7cff; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; }
                * { box-sizing: border-box; }
                body { margin:0; font: 14px/1.45 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--fg); }
                header { padding: 16px 20px; border-bottom: 1px solid #222; display:flex; justify-content: space-between; align-items:center; }
                header h1 { margin: 0; font-size: 16px; letter-spacing: 0.3px; }
                main { max-width: 1100px; margin: 0 auto; padding: 24px; }
                .row { display:flex; gap:16px; align-items:flex-end; flex-wrap:wrap; }
                input[type=url] { flex: 1; padding: 12px 12px; border-radius: 8px; border:1px solid #2a2d31; background: #0f1114; color: var(--fg); }
                input[type=number] { width: 110px; padding: 12px 12px; border-radius: 8px; border:1px solid #2a2d31; background: #0f1114; color: var(--fg); }
                button { padding: 10px 14px; border-radius: 8px; border:1px solid #2a2d31; background: var(--acc); color: #fff; cursor: pointer; font-weight:600; }
                button.secondary { background:#1d2025; color:var(--fg); }
                .stack { display:flex; flex-direction:column; gap:6px; }
                .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
                .card { background: var(--card); border:1px solid #202328; border-radius: 10px; padding:16px; }
                .muted { color: var(--muted); }
                .score { font-size: 36px; font-weight: 800; }
                .kvs { display:grid; grid-template-columns: 1fr 2fr; gap:8px 12px; }
                pre { background:#0f1114; border:1px solid #23262b; border-radius:8px; padding:12px; overflow:auto; max-height:320px; }
                ul { margin: 8px 0 0 20px; }
                .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#1d2025; border:1px solid #2a2d31; margin: 0 6px 6px 0; }
                .flex { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
                .small { font-size:12px; }
                .pages { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
                .page-card { border:1px solid #202328; border-radius:8px; padding:12px; background:#0f1114; }
                .page-card .page-url { font-weight:600; word-break:break-word; margin:4px 0 8px 0; }
                .page-header { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
                .page-info { flex:1 1 240px; }
                .page-stats { display:flex; gap:6px; flex-wrap:wrap; }
                .page-meta { display:flex; flex-wrap:wrap; gap:8px; font-size:12px; color: var(--muted); margin-top:8px; }
                .page-meta span { display:flex; align-items:center; }
                .page-meta span + span::before { content:"•"; margin:0 6px; color: var(--muted); }
                .page-section { margin-top:12px; }
                .page-breakdown { margin-top:6px; }
                .page-recs { background:#0f1114; border:1px solid #202328; border-radius:8px; padding:8px 12px; }
                .page-recs summary { cursor:pointer; font-size:12px; color: var(--muted); }
                .page-recs[open] { padding-bottom:12px; }
                .page-recs ul { margin-top:8px; }
                .page-empty { font-size:12px; color: var(--muted); margin-top:6px; }
                .keywords { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
                .keyword-row { display:flex; justify-content:space-between; align-items:center; background:#0f1114; border:1px solid #202328; border-radius:8px; padding:10px 12px; }
                .keyword-term { font-weight:600; }
                .keyword-meta { font-size:12px; color: var(--muted); }
                @media (max-width: 600px) {
                  .page-header { flex-direction:column; }
                  .page-stats { width:100%; }
                  .page-recs { width:100%; }
                  .page-meta span + span::before { margin:0 4px; }
                }
                @media (max-width: 920px) { .grid { grid-template-columns: 1fr; } }
              </style>
            </head>
            <body>
              <header>
                <h1>LLM Discoverability Audit</h1>
                <div class="muted small">Enter a URL and run audit</div>
              </header>
              <main>
                <div class="row">
                  <input id="url" type="url" placeholder="https://example.com" />
                  <div class="stack">
                    <label for="max-pages" class="muted small">Pages</label>
                    <input id="max-pages" type="number" min="1" max="20" value="1" />
                  </div>
                  <button id="audit">Run Audit</button>
                </div>
                <div id="status" class="muted" style="margin-top:10px;"></div>

                <div class="grid" style="margin-top:16px;">
                  <div class="card">
                    <div class="muted small">Score</div>
                    <div class="score" id="score">—</div>
                    <div class="muted small" style="margin-top:6px;">Breakdown</div>
                    <div id="breakdown" class="flex small"></div>
                  </div>
                  <div class="card">
                    <div class="muted small">Recommendations</div>
                    <ul id="recs"></ul>
                  </div>
                </div>

                <div class="grid" style="margin-top:16px;">
                  <div class="card">
                    <div class="muted small">Key Facts</div>
                    <div id="facts" class="kvs"></div>
                  </div>
                  <div class="card">
                    <div class="muted small">Generated llm.txt</div>
                    <div class="row" style="margin:8px 0 6px 0;">
                      <button class="secondary" id="copy">Copy</button>
                      <button class="secondary" id="download">Download</button>
                    </div>
                    <pre id="llmtxt"># run an audit to generate</pre>
                  </div>
                </div>

                <div id="keywords-card" class="card" style="margin-top:16px; display:none;">
                  <div class="muted small">LLM Keyword Outlook</div>
                  <div id="keywords" class="keywords"></div>
                </div>

                <div id="pages-card" class="card" style="margin-top:16px; display:none;">
                  <div class="muted small">Pages Audited</div>
                  <div id="pages" class="pages"></div>
                </div>
              </main>
              <script>
              const $ = (id)=>document.getElementById(id);
              const fmt = (v)=> v===null||v===undefined||v===""?"(missing)":v;
              const formatScore = (value) => {
                if (typeof value === 'number') {
                  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
                }
                if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) {
                  const num = Number(value);
                  return Number.isInteger(num) ? num.toString() : num.toFixed(1);
                }
                return value;
              };
              const pill = (k,v)=>`<span class="pill">${k}: <b>${formatScore(v)}</b></span>`;
              const maxPagesInput = $("max-pages");
              const pagesCard = $("pages-card");
              const pagesList = $("pages");
              const keywordsCard = $("keywords-card");
              const keywordsList = $("keywords");
              const orDefault = (value, fallback) => (value === undefined || value === null ? fallback : value);

              async function runAudit() {
                const url = $("url").value.trim();
                const maxPages = Math.max(1, parseInt(maxPagesInput.value, 10) || 1);
                if (!url) { $("status").textContent = "Please enter a URL"; return; }
                $("status").textContent = `Auditing up to ${maxPages} page(s)…`;
                $("audit").disabled = true;
                pagesCard.style.display = 'none';
                pagesList.innerHTML = '';
                keywordsCard.style.display = 'none';
                keywordsList.innerHTML = '';
                try {
                  const res = await fetch('/api/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, max_pages: maxPages })
                  });
                  if (!res.ok) throw new Error('Request failed');
                  const data = await res.json();
                  // Score + breakdown
                  if (data.score === undefined || data.score === null) {
                    $("score").textContent = '—';
                  } else {
                    $("score").textContent = `${data.score}/100`;
                  }
                  const bd = data.breakdown || {};
                  $("breakdown").innerHTML = Object.keys(bd).sort().map(k=>pill(k, bd[k])).join('');
                  // Recs
                  $("recs").innerHTML = (data.recommendations||[]).map(r=>`<li>${r}</li>`).join('');
                  // Facts
                  const p = data.page || {};
                  const pagesCount = orDefault(data.sampled_pages, (data.pages || []).length || 0);
                  const facts = [
                    ['Pages audited', fmt(pagesCount)],
                    ['URL', fmt(p.url)],
                    ['Status', fmt(p.status_code)],
                    ['Title', fmt(p.title)],
                    ['Description', fmt(p.description)],
                    ['Canonical', fmt(p.canonical)],
                    ['JSON-LD types', (p.json_ld_types||[]).join(', ')||'(none)'],
                    ['Word count', fmt(p.word_count)],
                    ['Reading ease', p.reading_ease!=null? p.reading_ease.toFixed(1): '(n/a)'],
                    ['Has FAQ schema', p.has_faq_schema? 'yes':'no'],
                    ['Robots blocked', data.page && data.page.blocked_by_robots? 'yes':'no'],
                    ['Sitemaps', (data.sitemaps||[]).join(', ')||'(none)'],
                    ['LLM policy present', data.llm_txt_found? 'yes':'no']
                  ];
                  $("facts").innerHTML = facts.map(([k,v])=>`<div class="muted">${k}</div><div>${v}</div>`).join('');
                  // llm.txt
                  $("llmtxt").textContent = data.llm_txt_draft || '# none';
                  const keywordSummary = data.keywords || [];
                  if (keywordSummary.length) {
                    const rows = keywordSummary.map(kw => {
                      const pages = kw.pages === 1 ? 'page' : 'pages';
                      return `
                        <div class="keyword-row">
                          <div class="keyword-term">${kw.term}</div>
                          <div class="keyword-meta">${kw.score}/100 · ${kw.pages} ${pages}</div>
                        </div>
                      `;
                    }).join('');
                    keywordsCard.style.display = 'block';
                    keywordsList.innerHTML = rows;
                  } else {
                    keywordsCard.style.display = 'none';
                    keywordsList.innerHTML = '';
                  }
                  const pages = data.pages || [];
                  if (pages.length) {
                    const cards = pages.map((p, idx) => {
                      const score = p.score!=null ? `${p.score}/100` : '—';
                      const status = orDefault(p.status_code, '—');
                      const words = orDefault(p.word_count, '—');
                      const reading = typeof p.reading_ease === 'number' ? p.reading_ease.toFixed(1) : '—';
                      const faq = p.has_faq_schema ? 'yes' : 'no';
                      const pageKeywords = (p.keywords || []).slice(0, 3).map(kw => `<span class="pill">${kw.term} (${kw.score}/100)</span>`).join('');
                      const keywordsSection = pageKeywords ? `
                        <div class="page-section">
                          <div class="muted small">Top keywords</div>
                          <div class="flex small">${pageKeywords}</div>
                        </div>
                      ` : '';
                      const breakdownEntries = Object.entries(p.breakdown || {});
                      const sortedBreakdown = breakdownEntries.sort((a, b) => (parseFloat(b[1]) || 0) - (parseFloat(a[1]) || 0));
                      const breakdownSection = sortedBreakdown.length ? `
                        <div class="page-section">
                          <div class="muted small">Weighted breakdown</div>
                          <div class="page-breakdown flex small">${sortedBreakdown.map(([k, v]) => pill(k, v)).join('')}</div>
                        </div>
                      ` : '';
                      const pageRecs = Array.isArray(p.recommendations) ? p.recommendations : [];
                      const recSection = pageRecs.length ? `
                        <div class="page-section">
                          <details class="page-recs">
                            <summary>Recommendations (${pageRecs.length})</summary>
                            <ul>${pageRecs.map(rec => `<li>${rec}</li>`).join('')}</ul>
                          </details>
                        </div>
                      ` : `
                        <div class="page-section">
                          <div class="muted small">Recommendations</div>
                          <div class="page-empty">No recommendations for this page.</div>
                        </div>
                      `;
                      const metaItems = [
                        `words: ${words}`,
                        `reading ease: ${reading}`,
                        `faq schema: ${faq}`,
                      ].map(text => `<span>${text}</span>`).join('');
                      return `
                        <div class="page-card">
                          <div class="page-header">
                            <div class="page-info">
                              <div class="muted small">Page ${idx + 1}</div>
                              <div class="page-url">${fmt(p.url)}</div>
                            </div>
                            <div class="page-stats small">
                              <span class="pill">score: ${score}</span>
                              <span class="pill">status: ${status}</span>
                            </div>
                          </div>
                          <div class="page-meta">${metaItems}</div>
                          ${keywordsSection}
                          ${breakdownSection}
                          ${recSection}
                        </div>
                      `;
                    }).join('');
                    pagesCard.style.display = 'block';
                    pagesList.innerHTML = cards;
                  } else {
                    pagesCard.style.display = 'none';
                    pagesList.innerHTML = '';
                  }
                  const totalPages = orDefault(data.sampled_pages, pages.length);
                  $("status").textContent = `Done. Audited ${totalPages} page(s).`;
                } catch (e) {
                  console.error(e);
                  $("status").textContent = "Error running audit. See console.";
                } finally {
                  $("audit").disabled = false;
                }
              }

              function copyTxt() {
                const txt = $("llmtxt").textContent || '';
                navigator.clipboard.writeText(txt);
                $("status").textContent = "Copied llm.txt to clipboard";
              }
              function downloadTxt() {
                const txt = $("llmtxt").textContent || '';
                const blob = new Blob([txt], {type:'text/plain'});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'llm.txt';
                document.body.appendChild(a);
                a.click();
                a.remove();
              }
              $("audit").addEventListener('click', runAudit);
              $("copy").addEventListener('click', copyTxt);
              $("download").addEventListener('click', downloadTxt);
              </script>
            </body>
            </html>
            """
        ).strip()
        return Response(html, mimetype="text/html")

    @app.post("/api/audit")
    def api_audit():
        try:
            payload: Dict[str, Any] = request.get_json(force=True) or {}
            url = str(payload.get("url", "")).strip()
            if not url:
                return jsonify({"error": "Missing 'url'"}), 400
            try:
                max_pages = int(payload.get("max_pages", 1))
            except (TypeError, ValueError):
                max_pages = 1
            site = audit_url(url, max_pages=max_pages)
            llm_txt = generate_llm_txt(site.base_url, sitemaps=site.sitemaps)
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
                    "keywords": [
                        {
                            "term": kw.term,
                            "score": kw.score,
                            "frequency": kw.frequency,
                            "in_title": kw.in_title,
                            "in_headings": kw.in_headings,
                            "in_description": kw.in_description,
                        }
                        for kw in p.keywords
                    ],
                    "recommendations": p.recommendations,
                }
                for p in site.pages
            ]
            data = {
                "score": site.score,
                "breakdown": site.breakdown,
                "recommendations": site.recommendations,
                "sampled_pages": len(site.pages),
                "pages": pages_payload,
                "keywords": [
                    {
                        "term": kw.term,
                        "score": kw.score,
                        "pages": kw.pages,
                    }
                    for kw in site.keywords
                ],
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
                    "keywords": [
                        {
                            "term": kw.term,
                            "score": kw.score,
                            "frequency": kw.frequency,
                            "in_title": kw.in_title,
                            "in_headings": kw.in_headings,
                            "in_description": kw.in_description,
                        }
                        for kw in (site.page.keywords if site.page else [])
                    ],
                },
                "llm_txt_found": site.llm_txt_found,
                "llm_txt_url": site.llm_txt_url,
                "sitemaps": site.sitemaps,
                "llm_txt_draft": llm_txt,
            }
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the LLM SEO web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
