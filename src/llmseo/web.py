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
                button { padding: 10px 14px; border-radius: 8px; border:1px solid #2a2d31; background: var(--acc); color: #fff; cursor: pointer; font-weight:600; }
                button.secondary { background:#1d2025; color:var(--fg); }
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
                  <div class="card" style="grid-column: span 2;">
                    <div class="muted small">Likely LLM topics</div>
                    <div id="topics" class="flex small"></div>
                  </div>
                </div>
              </main>
              <script>
              const $ = (id)=>document.getElementById(id);
              const fmt = (v)=> v===null||v===undefined||v===""?"(missing)":v;
              const pill = (k,v)=>`<span class="pill">${k}: <b>${v}</b></span>`;

              async function runAudit() {
                const url = $("url").value.trim();
                if (!url) { $("status").textContent = "Please enter a URL"; return; }
                $("status").textContent = "Auditing…";
                $("audit").disabled = true;
                try {
                  const res = await fetch('/api/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                  });
                  if (!res.ok) throw new Error('Request failed');
                  const data = await res.json();
                  // Score + breakdown
                  $("score").textContent = `${data.score ?? '—'}` + '/100';
                  const bd = data.breakdown || {};
                  $("breakdown").innerHTML = Object.keys(bd).sort().map(k=>pill(k, bd[k])).join('');
                  // Recs
                  $("recs").innerHTML = (data.recommendations||[]).map(r=>`<li>${r}</li>`).join('');
                  // Facts
                  const p = data.page || {};
                  const facts = [
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
                  const topics = p.topics || [];
                  $("topics").innerHTML = topics.length
                    ? topics.map(t=>pill(t.topic, `${Math.round(t.score)}/100`)).join('')
                    : "<span class='muted'>No strong topics detected</span>";
                  // llm.txt
                  $("llmtxt").textContent = data.llm_txt_draft || '# none';
                  $("status").textContent = "Done";
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
            site = audit_url(url)
            llm_txt = generate_llm_txt(site.base_url, sitemaps=site.sitemaps)
            data = {
                "score": site.score,
                "breakdown": site.breakdown,
                "recommendations": site.recommendations,
                "page": {
                    "url": site.page.url if site.page else None,
                    "status_code": site.page.status_code if site.page else None,
                    "title": site.page.title if site.page else None,
                    "description": site.page.description if site.page else None,
                    "canonical": site.page.canonical if site.page else None,
                    "og": site.page.og_tags if site.page else None,
                    "json_ld_types": site.page.json_ld_types if site.page else None,
                    "reading_ease": site.page.reading_ease if site.page else None,
                    "word_count": site.page.text_stats["word_count"] if site.page else None,
                    "has_faq_schema": site.page.has_faq_schema if site.page else None,
                    "blocked_by_robots": site.page.blocked_by_robots if site.page else None,
                    "topics": [
                        {"topic": t.topic, "score": t.score}
                        for t in (site.page.topics if site.page else [])
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

