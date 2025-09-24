**Overview**
- Audits a website URL for LLM discoverability.
- Generates a draft `llm.txt` you can publish at `/.well-known/llm.txt`.
- Produces a 0–100 score, a breakdown, and actionable recommendations.
- Samples up to N internal pages and averages findings for a broader view.
- Highlights likely LLM keywords with a quality score for each term.

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
- Basic audit (single page):
  ```bash
  PYTHONPATH=./src python -m llmseo.cli https://example.com
  ```
- Crawl multiple internal pages and save outputs:
  ```bash
  PYTHONPATH=./src python -m llmseo.cli https://example.com --max-pages 5 --json --save-llm-txt --out-dir ./out > report.json
  ```
- The published console output lists per-page scores, average breakdowns, and domain-level recommendations.

**Web UI**
- Launch the local UI:
  ```bash
  PYTHONPATH=./src python -m llmseo.web --host 127.0.0.1 --port 5173 --debug
  # Or try port 8080 if 5173 doesn't work:
  PYTHONPATH=./src python -m llmseo.web --host 0.0.0.0 --port 8080 --debug
  ```
- Open `http://127.0.0.1:5173` or `http://localhost:8080` and enter a URL to audit.
- Set the **Pages** input to sample additional internal URLs (results appear in the "Pages Audited" list).
- The UI shows the averaged score/breakdown, per-page snapshots, recommendations, and a generated `llm.txt` ready to copy or download.
- Review the "LLM Keyword Outlook" card to see which queries the page is best positioned to answer, alongside confidence scores and page coverage counts.

**What It Checks**
- Indexability: robots.txt and meta robots signals.
- Metadata: title, description, canonical, lang, OpenGraph.
- Structure: H1/H2/H3 usage and semantic HTML tags.
- Structured Data: JSON-LD types (FAQPage, Article, etc.).
- Content Depth: word count and Flesch reading ease.
- LLM Keyword Outlook: top thematic keywords and their relative likelihood for surfacing in LLM answers.
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

**CI / Automation**
- `.github/workflows/ci.yml` installs the package, runs smoke-import tests, and executes `llm-seo` against `https://example.com` with `--max-pages 3`.
- Each run uploads `audit.json` and the generated `llm.txt` as GitHub Action artifacts for quick review.

**Next Steps**
- Allow supplying seed URLs or sitemap.xml inputs to guide the crawl queue.
- Export a formatted HTML/Markdown report that bundles key findings and llm.txt.
- Explore a lightweight Node.js wrapper for environments without Python.
