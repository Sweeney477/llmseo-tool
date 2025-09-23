**Overview**
- Audits a website URL for LLM discoverability.
- Generates a draft `llm.txt` you can publish at `/.well-known/llm.txt`.
- Produces a 0–100 score, a breakdown, and actionable recommendations.

**Install**
- Requires Python 3.9+.
- From this folder:
  ```bash
  # Install dependencies
  pip install requests beautifulsoup4 Flask
  
  # Install the package (alternative to pip install -e .)
  pip install .
  ```

**Usage**
- Basic audit:
  ```bash
  PYTHONPATH=./src python -m llmseo.cli https://example.com
  ```
- Save a generated `llm.txt`:
  ```bash
  PYTHONPATH=./src python -m llmseo.cli https://example.com --save-llm-txt --out-dir ./out
  ```
- JSON output (for pipelines):
  ```bash
  PYTHONPATH=./src python -m llmseo.cli https://example.com --json > report.json
  ```

**Web UI**
- Launch the local UI:
  ```bash
  PYTHONPATH=./src python -m llmseo.web --host 127.0.0.1 --port 5173 --debug
  # Or try port 8080 if 5173 doesn't work:
  PYTHONPATH=./src python -m llmseo.web --host 0.0.0.0 --port 8080 --debug
  ```
- Open `http://127.0.0.1:5173` or `http://localhost:8080` and enter a URL to audit.
- The UI shows score, breakdown, key facts, recommendations, and a generated `llm.txt` that you can copy or download.

**What It Checks**
- Indexability: robots.txt and meta robots signals.
- Metadata: title, description, canonical, lang, OpenGraph.
- Structure: H1/H2/H3 usage and semantic HTML tags.
- Structured Data: JSON-LD types (FAQPage, Article, etc.).
- Content Depth: word count and Flesch reading ease.
- LLM Policy: presence of `/.well-known/llm.txt` or `/llm.txt`.
- Sitemaps: discovered via robots.txt.

**llm.txt**
- A human-readable preference file for LLM crawlers/trainers (complements `robots.txt`).
- The tool drafts a sensible starting file. Publish it at `/.well-known/llm.txt` on your site.

**Notes & Limits**
- Network fetching depends on your environment (firewalls, auth, etc.).
- HTML parsing is light-weight; extremely dynamic pages may need server‑rendered fallbacks for best results.
- The score is heuristic—use it to guide improvements, not as an absolute metric.

**Troubleshooting**
- If `pip install -e .` fails, try `pip install .` instead
- If commands aren't found, use the full module path: `PYTHONPATH=./src python -m llmseo.cli`
- If web UI won't connect, try different ports (8080, 3000) or hosts (0.0.0.0)
- On macOS, you may need to accept Xcode license: `sudo xcodebuild -license accept`

**Next Steps**
- Want a small crawler over multiple internal pages? I can extend the tool to sample N pages and aggregate scores.
- Prefer a Node.js version or GitHub Action? I can add that too.
