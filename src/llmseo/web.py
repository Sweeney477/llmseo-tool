from __future__ import annotations

import argparse
from textwrap import dedent
from typing import Any, Dict, List
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request

from .audit import audit_url
from .llm_txt import generate_llm_txt

DEFAULT_CONTACT_EMAIL = "webmaster@domain"
DEFAULT_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
MAX_LIST_ITEMS = 10


def _clean_string(value: Any, *, max_length: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = "".join(ch for ch in value if ch.isprintable()).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].strip()
    return cleaned


def sanitize_contact(value: Any) -> str:
    cleaned = _clean_string(value, max_length=254)
    if not cleaned:
        return DEFAULT_CONTACT_EMAIL
    if " " in cleaned or cleaned.count("@") != 1:
        return DEFAULT_CONTACT_EMAIL
    local, domain = cleaned.split("@", 1)
    if not local or not domain:
        return DEFAULT_CONTACT_EMAIL
    return cleaned


def sanitize_license_url(value: Any) -> str:
    cleaned = _clean_string(value, max_length=500)
    if not cleaned:
        return DEFAULT_LICENSE_URL
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return DEFAULT_LICENSE_URL
    return cleaned


def _prepare_items(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        normalized = value.replace("\r", "\n")
        raw_items = []
        for part in normalized.split("\n"):
            raw_items.extend(part.split(","))
    else:
        raw_items = []
    cleaned_items: List[str] = []
    for item in raw_items:
        cleaned = _clean_string(item, max_length=200)
        if cleaned:
            cleaned_items.append(cleaned)
    return cleaned_items


def sanitize_url_list(value: Any) -> List[str]:
    items: List[str] = []
    for candidate in _prepare_items(value):
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            items.append(candidate)
        if len(items) >= MAX_LIST_ITEMS:
            break
    return items


def sanitize_string_list(value: Any) -> List[str]:
    items: List[str] = []
    for candidate in _prepare_items(value):
        items.append(candidate)
        if len(items) >= MAX_LIST_ITEMS:
            break
    return items


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
                :root { --bg:#0c0d0f; --fg:#e8e8ea; --muted:#a7a7ad; --card:#15171a; --panel:#101217; --acc:#4f7cff; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; }
                * { box-sizing: border-box; }
                body { margin:0; font: 14px/1.45 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--fg); }
                header { padding: 16px 24px; border-bottom: 1px solid #1b1d21; display:flex; justify-content: space-between; align-items:center; gap:16px; }
                header h1 { margin: 0; font-size: 16px; letter-spacing: 0.3px; }
                header .muted { max-width: 420px; }
                main { max-width: 1280px; margin: 0 auto; padding: 28px 24px 40px; display:grid; gap:20px; grid-template-columns: 280px minmax(0, 1fr) 300px; align-items:start; }
                .card { background: var(--card); border:1px solid #202328; border-radius: 12px; padding:18px; }
                .muted { color: var(--muted); }
                .small { font-size:12px; }
                .stack { display:flex; flex-direction:column; gap:6px; }
                .row { display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap; }
                label { font-size:12px; color: var(--muted); text-transform: uppercase; letter-spacing:0.6px; }
                input[type=url], input[type=email], input[type=text], input[type=number] { width:100%; padding: 10px 12px; border-radius: 8px; border:1px solid #23262b; background: #11131a; color: var(--fg); font: inherit; }
                input[type=number] { max-width: 120px; }
                textarea { width:100%; padding: 12px; border-radius: 8px; border:1px solid #23262b; background:#11131a; color: var(--fg); font: inherit; resize: vertical; min-height: 96px; }
                button { padding: 10px 14px; border-radius: 8px; border:1px solid transparent; background: var(--acc); color: #fff; cursor: pointer; font-weight:600; transition: transform 120ms ease, background 120ms ease; }
                button:hover { transform: translateY(-1px); }
                button.secondary { background:#1d2025; color:var(--fg); border-color:#2a2d31; }
                button.secondary:hover { background:#242831; }
                .workspace-controls { position:sticky; top:84px; display:flex; flex-direction:column; gap:16px; }
                .control-card { display:flex; flex-direction:column; gap:14px; background: var(--panel); border-color:#1c1f26; }
                .control-card h2 { margin:0; font-size:12px; letter-spacing:0.6px; text-transform:uppercase; color:var(--muted); }
                .status-message { min-height: 18px; }
                .workspace-main { display:flex; flex-direction:column; gap:16px; }
                .tab-bar { display:flex; gap:8px; padding:4px; background:#11131a; border-radius:12px; border:1px solid #1f232a; width:fit-content; }
                .tab { background:transparent; color:var(--muted); border-radius:8px; padding:8px 14px; border: none; font-weight:600; cursor:pointer; }
                .tab.active { background: var(--acc); color:#fff; }
                .tab-panel { display:none; }
                .tab-panel.active { display:flex; flex-direction:column; gap:16px; }
                .hero-card { display:flex; gap:24px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; }
                .score { font-size: 40px; font-weight: 800; }
                .score sup { font-size:16px; font-weight:600; color:var(--muted); margin-left:4px; }
                .breakdown-pills { display:flex; gap:8px; flex-wrap:wrap; }
                .pill { display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:999px; background:#1d2025; border:1px solid #2a2d31; font-size:12px; }
                .overview-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:16px; }
                .kvs { display:grid; grid-template-columns: 1fr 1fr; gap:8px 12px; align-items:start; }
                .spaced-list { margin:12px 0 0 16px; padding:0; display:flex; flex-direction:column; gap:8px; }
                .spaced-list li { line-height:1.45; }
                .keywords { display:flex; flex-direction:column; gap:8px; }
                .keyword-row { display:flex; justify-content:space-between; align-items:center; border:1px solid #23262b; border-radius:10px; padding:10px 12px; background:#11131a; }
                .keyword-term { font-weight:600; }
                .keyword-meta { font-size:12px; color:var(--muted); }
                .table-wrapper { overflow:auto; border-radius:10px; border:1px solid #202328; }
                table { width:100%; border-collapse:collapse; }
                thead { background:#11131a; }
                th, td { padding:12px 14px; text-align:left; border-bottom:1px solid #1f232a; font-size:13px; }
                tbody tr { cursor:pointer; transition: background 120ms ease; }
                tbody tr:hover { background:#161a21; }
                tbody tr.selected { background:#1e293b; }
                .badge { display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:999px; background:#1d2025; border:1px solid #2a2d31; font-size:11px; text-transform:uppercase; letter-spacing:0.6px; }
                .page-detail { display:none; flex-direction:column; gap:12px; }
                .page-detail.active { display:flex; }
                .page-detail h3 { margin:0; font-size:15px; }
                .meta-grid { display:flex; flex-wrap:wrap; gap:10px 18px; font-size:12px; color:var(--muted); }
                .detail-section { border-top:1px solid #1f232a; padding-top:12px; }
                .detail-section:first-of-type { border-top:none; padding-top:0; }
                .detail-section h4 { margin:0 0 8px; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:0.6px; }
                .detail-section ul { margin:0; padding-left:18px; display:flex; flex-direction:column; gap:6px; }
                .detail-pills { display:flex; gap:8px; flex-wrap:wrap; }
                .empty-state { padding:18px; border:1px dashed #2a2d31; border-radius:10px; text-align:center; background:#11131a; }
                .policy-rail { display:flex; flex-direction:column; gap:16px; position:sticky; top:84px; }
                .policy-rail .card { background: var(--panel); border-color:#1c1f26; }
                .policy-actions { display:flex; flex-wrap:wrap; gap:8px; }
                pre { background:#0f1114; border:1px solid #23262b; border-radius:10px; padding:14px; overflow:auto; max-height:380px; }
                .microcopy { font-size:12px; color:var(--muted); line-height:1.45; }
                a { color: var(--acc); }
                @media (max-width: 1180px) {
                  main { grid-template-columns: 260px minmax(0,1fr); }
                  .policy-rail { position:static; }
                }
                @media (max-width: 960px) {
                  main { grid-template-columns: minmax(0,1fr); }
                  .workspace-controls { position:static; }
                  .policy-rail { order:3; }
                }
                @media (max-width: 600px) {
                  header { flex-direction:column; align-items:flex-start; }
                  .tab-bar { width:100%; }
                  .tab { flex:1; text-align:center; }
                }
              </style>
            </head>
            <body>
              <header>
                <h1>LLM Discoverability Audit</h1>
                <div class="muted small">Enter a URL and run audit</div>
              </header>
              <main>
                <aside class="workspace-controls">
                  <div class="card control-card">
                    <div class="stack">
                      <label for="url">Website URL</label>
                      <input id="url" type="url" placeholder="https://example.com" />
                    </div>
                    <div class="row">
                      <div class="stack" style="max-width:120px;">
                        <label for="max-pages">Pages</label>
                        <input id="max-pages" type="number" min="1" max="20" value="1" />
                      </div>
                      <button id="audit" style="flex:1;">Run audit</button>
                    </div>
                    <div id="status" class="status-message muted small"></div>
                  </div>
                  <div class="card control-card">
                    <h2>Contact &amp; licensing</h2>
                    <div class="stack">
                      <label for="contact-email">Contact email</label>
                      <input id="contact-email" type="email" placeholder="webmaster@example.com" value="webmaster@domain" />
                    </div>
                    <div class="stack">
                      <label for="license-url">License URL</label>
                      <input id="license-url" type="url" placeholder="https://example.com/license" value="https://creativecommons.org/licenses/by/4.0/" />
                    </div>
                  </div>
                  <div class="card control-card">
                    <h2>Contextual sources</h2>
                    <div class="stack">
                      <label for="preferred-sources">Preferred sources</label>
                      <textarea id="preferred-sources" rows="3" placeholder="https://example.com/about&#10;https://example.com/research"></textarea>
                      <div class="microcopy">One URL per line or comma separated.</div>
                    </div>
                    <div class="stack">
                      <label for="apis">APIs</label>
                      <textarea id="apis" rows="3" placeholder="https://api.example.com/v1/docs"></textarea>
                      <div class="microcopy">One endpoint per line or comma separated.</div>
                    </div>
                  </div>
                </aside>

                <section class="workspace-main">
                  <div class="tab-bar">
                    <button class="tab active" data-tab="overview">Overview</button>
                    <button class="tab" data-tab="pages">Pages</button>
                    <button class="tab" data-tab="policy">LLM Policy</button>
                  </div>

                  <section class="tab-panel active" id="tab-overview">
                    <div class="card hero-card">
                      <div>
                        <div class="muted small">Site score</div>
                        <div class="score" id="score">—</div>
                      </div>
                      <div style="min-width:220px;">
                        <div class="muted small" style="margin-bottom:6px;">Breakdown</div>
                        <div id="breakdown" class="breakdown-pills small"></div>
                      </div>
                    </div>

                    <div class="overview-grid">
                      <div class="card">
                        <div class="muted small">Top recommendations</div>
                        <ul id="recs" class="spaced-list"></ul>
                      </div>
                      <div class="card">
                        <div class="muted small">Key facts</div>
                        <div id="facts" class="kvs"></div>
                      </div>
                      <div id="keywords-card" class="card" style="display:none;">
                        <div class="muted small">LLM keyword outlook</div>
                        <div id="keywords" class="keywords"></div>
                      </div>
                    </div>
                  </section>

                  <section class="tab-panel" id="tab-pages">
                    <div class="card">
                      <div class="muted small" style="margin-bottom:8px;">Pages audited</div>
                      <div class="table-wrapper">
                        <table>
                          <thead>
                            <tr>
                              <th scope="col">Page</th>
                              <th scope="col">Score</th>
                              <th scope="col">Status</th>
                              <th scope="col">Keywords</th>
                            </tr>
                          </thead>
                          <tbody id="pages-table"></tbody>
                        </table>
                      </div>
                      <div id="pages-empty" class="empty-state muted small">Run an audit to populate page-level insights.</div>
                    </div>
                    <div id="page-detail" class="card page-detail">
                      <div class="muted small">Select a page to review granular recommendations.</div>
                    </div>
                  </section>

                  <section class="tab-panel" id="tab-policy">
                    <div class="card">
                      <div class="muted small">Generated llm.txt draft</div>
                      <pre id="llmtxt"># run an audit to generate</pre>
                    </div>
                    <div class="card">
                      <div class="muted small">Live policy status</div>
                      <div id="llm-status" class="microcopy" style="margin-top:6px;">Awaiting audit.</div>
                      <div id="llm-location" class="microcopy" style="margin-top:6px;"></div>
                    </div>
                  </section>
                </section>

                <aside class="policy-rail">
                  <div class="card">
                    <div class="muted small">Quick actions</div>
                    <div class="microcopy" style="margin-top:6px;">Share outputs or keep iterating on the crawl settings.</div>
                    <div class="policy-actions" style="margin-top:12px;">
                      <button class="secondary" id="copy">Copy llm.txt</button>
                      <button class="secondary" id="download">Download llm.txt</button>
                      <button class="secondary" id="download-json" disabled>Download JSON</button>
                    </div>
                  </div>
                  <div class="card">
                    <div class="muted small">Guidance</div>
                    <div class="microcopy" style="margin-top:6px;">Use the Overview tab for leadership-ready highlights, the Pages tab to triage issues, and the LLM Policy tab before publishing.</div>
                  </div>
                </aside>
              </main>
              <script>
              const $ = (id) => document.getElementById(id);
              const fmt = (v) => (v === null || v === undefined || v === '' ? '(missing)' : v);
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
              const pill = (k, v) => `<span class="pill">${k}: <b>${formatScore(v)}</b></span>`;
              const orDefault = (value, fallback) => (value === undefined || value === null ? fallback : value);
              const joinList = (values) => (Array.isArray(values) ? values.join('\n') : '');
              const STORAGE_KEY = 'llmseo:ui';
              const RESULT_KEY = 'llmseo:last-result';
              let suppressSave = false;
              const urlInput = $('url');
              const maxPagesInput = $('max-pages');
              const contactInput = $('contact-email');
              const licenseInput = $('license-url');
              const preferredSourcesInput = $('preferred-sources');
              const apisInput = $('apis');
              const auditButton = $('audit');
              const statusEl = $('status');
              const keywordsCard = $('keywords-card');
              const keywordsList = $('keywords');
              const downloadJsonBtn = $('download-json');
              const pagesTableBody = $('pages-table');
              const pagesEmpty = $('pages-empty');
              const pageDetail = $('page-detail');
              const llmStatus = $('llm-status');
              const llmLocation = $('llm-location');
              const tabs = Array.from(document.querySelectorAll('.tab'));
              const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));
              let currentTab = 'overview';
              let lastAuditResult = null;
              let pagesCache = [];
              let selectedPageIndex = -1;
              const inputFields = [urlInput, maxPagesInput, contactInput, licenseInput, preferredSourcesInput, apisInput];
              inputFields.forEach((field) => {
                field.addEventListener('input', () => saveUiState());
              });
              function selectTab(name) {
                if (!name) {
                  return;
                }
                currentTab = name;
                tabs.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === name));
                tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${name}`));
                saveUiState();
              }
              tabs.forEach((btn) => {
                btn.addEventListener('click', () => selectTab(btn.dataset.tab));
              });
              function saveUiState() {
                if (suppressSave) {
                  return;
                }
                const payload = {
                  url: urlInput.value,
                  maxPages: maxPagesInput.value,
                  contact: contactInput.value,
                  license: licenseInput.value,
                  preferredSources: preferredSourcesInput.value,
                  apis: apisInput.value,
                  tab: currentTab,
                };
                try {
                  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
                } catch (err) {
                  console.debug('Unable to persist UI state', err);
                }
              }
              function restoreUiState() {
                try {
                  const raw = localStorage.getItem(STORAGE_KEY);
                  if (!raw) {
                    return;
                  }
                  const payload = JSON.parse(raw);
                  suppressSave = true;
                  if (payload.url) {
                    urlInput.value = payload.url;
                  }
                  if (payload.maxPages) {
                    maxPagesInput.value = payload.maxPages;
                  }
                  if (payload.contact) {
                    contactInput.value = payload.contact;
                  }
                  if (payload.license) {
                    licenseInput.value = payload.license;
                  }
                  if (payload.preferredSources) {
                    preferredSourcesInput.value = payload.preferredSources;
                  }
                  if (payload.apis) {
                    apisInput.value = payload.apis;
                  }
                  if (payload.tab) {
                    selectTab(payload.tab);
                  }
                } catch (err) {
                  console.debug('Unable to restore UI state', err);
                } finally {
                  suppressSave = false;
                }
              }
              function persistResult(data) {
                try {
                  localStorage.setItem(RESULT_KEY, JSON.stringify(data));
                } catch (err) {
                  console.debug('Unable to persist audit result', err);
                }
              }
              function restoreAuditResult() {
                try {
                  const raw = localStorage.getItem(RESULT_KEY);
                  if (!raw) {
                    return;
                  }
                  const data = JSON.parse(raw);
                  applyAuditResult(data);
                  statusEl.textContent = 'Restored previous audit.';
                } catch (err) {
                  console.debug('Unable to restore audit result', err);
                }
              }
              function renderKeywords(keywordSummary) {
                if (!Array.isArray(keywordSummary) || keywordSummary.length === 0) {
                  keywordsCard.style.display = 'none';
                  keywordsList.innerHTML = '';
                  return;
                }
                const rows = keywordSummary
                  .map((kw) => {
                    const pages = kw.pages === 1 ? 'page' : 'pages';
                    return `
                        <div class="keyword-row">
                          <div class="keyword-term">${kw.term}</div>
                          <div class="keyword-meta">${kw.score}/100 · ${kw.pages} ${pages}</div>
                        </div>
                      `;
                  })
                  .join('');
                keywordsCard.style.display = 'block';
                keywordsList.innerHTML = rows;
              }
              function renderPages(pages) {
                pagesCache = Array.isArray(pages) ? pages : [];
                selectedPageIndex = -1;
                if (!pagesCache.length) {
                  pagesTableBody.innerHTML = '';
                  pagesEmpty.style.display = 'block';
                  pageDetail.classList.remove('active');
                  pageDetail.innerHTML = '<div class="muted small">Select a page to review granular recommendations.</div>';
                  return;
                }
                pagesEmpty.style.display = 'none';
                const rows = pagesCache
                  .map((p, idx) => {
                    const displayTitle = p.title && p.title.trim() ? p.title : p.url || '(missing)';
                    const urlLine = p.url ? `<div class="muted small">${p.url}</div>` : '';
                    const score = p.score !== undefined && p.score !== null ? `${p.score}/100` : '—';
                    const status = orDefault(p.status_code, '—');
                    const keywordCount = Array.isArray(p.keywords) ? p.keywords.length : 0;
                    const keywordPreview = keywordCount
                      ? p.keywords.slice(0, 2).map((kw) => kw.term).join(', ') + (keywordCount > 2 ? '…' : '')
                      : '';
                    const keywordLine = keywordCount
                      ? `<div class="muted small">${keywordPreview}</div>`
                      : '';
                    const keywordLabel = keywordCount
                      ? `${keywordCount} keyword${keywordCount === 1 ? '' : 's'}`
                      : '—';
                    return `
                      <tr data-index="${idx}">
                        <td>
                          <div>${displayTitle}</div>
                          ${urlLine}
                        </td>
                        <td>${score}</td>
                        <td>${status}</td>
                        <td>
                          <div>${keywordLabel}</div>
                          ${keywordLine}
                        </td>
                      </tr>
                    `;
                  })
                  .join('');
                pagesTableBody.innerHTML = rows;
                showPageDetail(0);
              }
              function showPageDetail(index) {
                if (!pagesCache[index]) {
                  return;
                }
                selectedPageIndex = index;
                const page = pagesCache[index];
                const score = page.score !== undefined && page.score !== null ? `${page.score}/100` : '—';
                const status = orDefault(page.status_code, '—');
                const words = orDefault(page.word_count, '—');
                const reading = typeof page.reading_ease === 'number' ? page.reading_ease.toFixed(1) : '—';
                const faq = page.has_faq_schema ? 'yes' : 'no';
                const displayTitle = page.title && page.title.trim() ? page.title : page.url || 'Untitled page';
                const keywordBadges = Array.isArray(page.keywords)
                  ? page.keywords.map((kw) => `<span class="pill">${kw.term} (${kw.score}/100)</span>`).join('')
                  : '';
                const breakdownEntries = Object.entries(page.breakdown || {});
                const sortedBreakdown = breakdownEntries.sort((a, b) => (parseFloat(b[1]) || 0) - (parseFloat(a[1]) || 0));
                const breakdownSection = sortedBreakdown.length
                  ? `
                        <div class="detail-section">
                          <h4>Weighted breakdown</h4>
                          <div class="detail-pills">${sortedBreakdown.map(([k, v]) => pill(k, v)).join('')}</div>
                        </div>
                      `
                  : '';
                const recommendations = Array.isArray(page.recommendations) ? page.recommendations : [];
                const recSection = recommendations.length
                  ? `
                        <div class="detail-section">
                          <h4>Recommendations (${recommendations.length})</h4>
                          <ul>${recommendations.map((rec) => `<li>${rec}</li>`).join('')}</ul>
                        </div>
                      `
                  : `
                        <div class="detail-section">
                          <h4>Recommendations</h4>
                          <div class="microcopy">No recommendations for this page.</div>
                        </div>
                      `;
                const keywordSection = keywordBadges
                  ? `
                        <div class="detail-section">
                          <h4>Keywords</h4>
                          <div class="detail-pills">${keywordBadges}</div>
                        </div>
                      `
                  : '';
                pageDetail.classList.add('active');
                pageDetail.innerHTML = `
                  <div class="badge">PAGE ${index + 1}</div>
                  <h3>${displayTitle}</h3>
                  ${page.url ? `<div class="microcopy">${page.url}</div>` : ''}
                  <div class="meta-grid">
                    <span>Score: ${score}</span>
                    <span>Status: ${status}</span>
                    <span>Words: ${words}</span>
                    <span>Reading ease: ${reading}</span>
                    <span>FAQ schema: ${faq}</span>
                    <span>Robots blocked: ${page.blocked_by_robots ? 'yes' : 'no'}</span>
                  </div>
                  ${keywordSection}
                  ${breakdownSection}
                  ${recSection}
                `;
                Array.from(pagesTableBody.children).forEach((row) => {
                  row.classList.toggle('selected', Number(row.dataset.index) === index);
                });
              }
              pagesTableBody.addEventListener('click', (event) => {
                const target = event.target;
                if (!(target instanceof Element)) {
                  return;
                }
                const row = target.closest('tr[data-index]');
                if (!row) {
                  return;
                }
                const idx = Number(row.dataset.index);
                if (!Number.isNaN(idx)) {
                  showPageDetail(idx);
                }
              });
              function updatePolicyStatus(data) {
                if (!llmStatus) {
                  return;
                }
                if (data.llm_txt_found) {
                  llmStatus.textContent = 'Live llm.txt detected.';
                  if (data.llm_txt_url) {
                    llmLocation.innerHTML = `<a href="${data.llm_txt_url}" target="_blank" rel="noopener">View published llm.txt</a>`;
                  } else {
                    llmLocation.textContent = '';
                  }
                } else {
                  llmStatus.textContent = 'No live llm.txt detected. Use the draft to publish guidance.';
                  if (data.llm_txt_url) {
                    llmLocation.textContent = `Expected at ${data.llm_txt_url}`;
                  } else {
                    llmLocation.textContent = '';
                  }
                }
              }
              function applyAuditResult(data) {
                lastAuditResult = data;
                downloadJsonBtn.disabled = false;
                if (data.llm_txt_options) {
                  const opts = data.llm_txt_options;
                  suppressSave = true;
                  contactInput.value = opts.contact || '';
                  licenseInput.value = opts.license_url || '';
                  preferredSourcesInput.value = joinList(opts.preferred_sources);
                  apisInput.value = joinList(opts.apis);
                  suppressSave = false;
                }
                const scoreEl = $('score');
                if (data.score === undefined || data.score === null) {
                  scoreEl.textContent = '—';
                } else {
                  scoreEl.innerHTML = `${formatScore(data.score)}<sup>/100</sup>`;
                }
                const bd = data.breakdown || {};
                const breakdownHtml = Object.keys(bd)
                  .sort()
                  .map((key) => pill(key, bd[key]))
                  .join('');
                $('breakdown').innerHTML = breakdownHtml || '<span class="microcopy">No data yet.</span>';
                const recs = Array.isArray(data.recommendations) ? data.recommendations : [];
                $('recs').innerHTML = recs.length
                  ? recs.map((r) => `<li>${r}</li>`).join('')
                  : '<li class="microcopy">No recommendations yet.</li>';
                const p = data.page || {};
                const pagesCount = orDefault(data.sampled_pages, (data.pages || []).length || 0);
                const facts = [
                  ['Pages audited', fmt(pagesCount)],
                  ['URL', fmt(p.url)],
                  ['Status', fmt(p.status_code)],
                  ['Title', fmt(p.title)],
                  ['Description', fmt(p.description)],
                  ['Canonical', fmt(p.canonical)],
                  ['JSON-LD types', (p.json_ld_types || []).join(', ') || '(none)'],
                  ['Word count', fmt(p.word_count)],
                  ['Reading ease', p.reading_ease != null ? p.reading_ease.toFixed(1) : '(n/a)'],
                  ['Has FAQ schema', p.has_faq_schema ? 'yes' : 'no'],
                  ['Robots blocked', p.blocked_by_robots ? 'yes' : 'no'],
                  ['Sitemaps', (data.sitemaps || []).join(', ') || '(none)'],
                  ['LLM policy present', data.llm_txt_found ? 'yes' : 'no'],
                ];
                $('facts').innerHTML = facts.map(([k, v]) => `<div class="muted">${k}</div><div>${v}</div>`).join('');
                $('llmtxt').textContent = data.llm_txt_draft || '# none';
                renderKeywords(data.keywords || []);
                renderPages(data.pages || []);
                updatePolicyStatus(data);
                saveUiState();
              }
              async function runAudit() {
                const url = urlInput.value.trim();
                const maxPages = Math.max(1, parseInt(maxPagesInput.value, 10) || 1);
                const contactEmail = contactInput.value.trim();
                const licenseUrl = licenseInput.value.trim();
                const preferredSources = preferredSourcesInput.value;
                const apis = apisInput.value;
                downloadJsonBtn.disabled = true;
                if (!url) {
                  statusEl.textContent = 'Please enter a URL';
                  return;
                }
                statusEl.textContent = `Auditing up to ${maxPages} page(s)…`;
                auditButton.disabled = true;
                renderPages([]);
                renderKeywords([]);
                try {
                  const res = await fetch('/api/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      url,
                      max_pages: maxPages,
                      contact_email: contactEmail,
                      license_url: licenseUrl,
                      preferred_sources: preferredSources,
                      apis,
                    }),
                  });
                  if (!res.ok) {
                    let errorText = `Request failed with status ${res.status}`;
                    let rawBody = '';
                    try {
                      rawBody = await res.text();
                    } catch (bodyError) {
                      console.error('Failed to read error response', bodyError);
                    }
                    const contentType = res.headers.get('content-type') || '';
                    if (rawBody) {
                      if (contentType.includes('application/json')) {
                        try {
                          const errorPayload = JSON.parse(rawBody);
                          if (errorPayload !== undefined && errorPayload !== null) {
                            const messageCandidates = [];
                            if (typeof errorPayload === 'string') {
                              messageCandidates.push(errorPayload);
                            }
                            if (Array.isArray(errorPayload)) {
                              errorPayload
                                .filter((item) => typeof item === 'string')
                                .forEach((item) => messageCandidates.push(item));
                            }
                            if (errorPayload && typeof errorPayload === 'object') {
                              ['error', 'message', 'detail'].forEach((key) => {
                                const value = errorPayload[key];
                                if (typeof value === 'string') {
                                  messageCandidates.push(value);
                                } else if (Array.isArray(value)) {
                                  value
                                    .filter((item) => typeof item === 'string')
                                    .forEach((item) => messageCandidates.push(item));
                                } else if (value && typeof value === 'object' && typeof value.message === 'string') {
                                  messageCandidates.push(value.message);
                                }
                              });
                            }
                            const messageFromPayload = messageCandidates
                              .map((msg) => msg.trim())
                              .find(Boolean);
                            if (messageFromPayload) {
                              errorText = messageFromPayload;
                            } else if (errorPayload && typeof errorPayload === 'object') {
                              const serialized = JSON.stringify(errorPayload);
                              if (serialized && serialized !== '{}') {
                                errorText = serialized;
                              }
                            }
                          }
                        } catch (jsonError) {
                          console.error('Failed to parse error response', jsonError);
                          const trimmedBody = rawBody.trim();
                          if (trimmedBody) {
                            errorText = trimmedBody;
                          }
                        }
                      } else {
                        const trimmedBody = rawBody.trim();
                        if (trimmedBody) {
                          errorText = trimmedBody;
                        }
                      }
                    }
                    if ((!rawBody || !rawBody.trim()) && res.statusText) {
                      errorText = `Request failed with status ${res.status} (${res.statusText})`;
                    }
                    statusEl.textContent = errorText;
                    throw new Error(errorText);
                  }
                  const data = await res.json();
                  applyAuditResult(data);
                  persistResult(data);
                  const totalPages = orDefault(data.sampled_pages, (data.pages || []).length || 0);
                  statusEl.textContent = `Done. Audited ${totalPages} page(s).`;
                } catch (e) {
                  console.error(e);
                  const fallbackMessage = 'Error running audit. Please try again.';
                  let message = fallbackMessage;
                  if (typeof e === 'string' && e.trim()) {
                    message = e.trim();
                  } else if (e && typeof e === 'object') {
                    const possibleMessage = typeof e.message === 'string' ? e.message.trim() : '';
                    if (possibleMessage) {
                      message = possibleMessage;
                    }
                  }
                  statusEl.textContent = message;
                  downloadJsonBtn.disabled = true;
                } finally {
                  auditButton.disabled = false;
                }
              }
              function copyTxt() {
                const txt = $('llmtxt').textContent || '';
                navigator.clipboard.writeText(txt);
                statusEl.textContent = 'Copied llm.txt to clipboard';
              }
              function downloadTxt() {
                const txt = $('llmtxt').textContent || '';
                const blob = new Blob([txt], { type: 'text/plain' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'llm.txt';
                document.body.appendChild(a);
                a.click();
                a.remove();
              }
              function downloadJson() {
                if (!lastAuditResult) {
                  return;
                }
                const blob = new Blob([JSON.stringify(lastAuditResult, null, 2)], { type: 'application/json' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'audit.json';
                document.body.appendChild(a);
                a.click();
                a.remove();
              }
              auditButton.addEventListener('click', runAudit);
              $('copy').addEventListener('click', copyTxt);
              $('download').addEventListener('click', downloadTxt);
              downloadJsonBtn.addEventListener('click', downloadJson);
              restoreUiState();
              restoreAuditResult();
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
            max_pages = max(1, min(max_pages, 20))
            contact_email = sanitize_contact(payload.get("contact_email"))
            license_url = sanitize_license_url(payload.get("license_url"))
            preferred_sources = sanitize_url_list(payload.get("preferred_sources"))
            apis = sanitize_string_list(payload.get("apis"))
            site = audit_url(url, max_pages=max_pages)
            llm_txt = generate_llm_txt(
                site.base_url,
                sitemaps=site.sitemaps,
                contact=contact_email,
                license_url=license_url,
                preferred_sources=preferred_sources,
                apis=apis,
            )
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
                "llm_txt_options": {
                    "contact": contact_email,
                    "license_url": license_url,
                    "preferred_sources": preferred_sources,
                    "apis": apis,
                },
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
