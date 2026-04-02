---
phase: rss-feed-pipeline
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - .gitignore
  - config.yaml
  - src/rss_feed/__init__.py
  - src/rss_feed/__main__.py
  - src/rss_feed/main.py
  - src/rss_feed/config.py
  - src/rss_feed/db.py
  - src/rss_feed/classifier.py
  - src/rss_feed/enricher.py
  - src/rss_feed/poller.py
  - src/rss_feed/feed_writer.py
  - src/rss_feed/server.py
  - tests/rss_feed/__init__.py
  - tests/rss_feed/conftest.py
  - tests/rss_feed/test_config.py
  - tests/rss_feed/test_db.py
  - tests/rss_feed/test_classifier.py
  - tests/rss_feed/test_enricher.py
  - tests/rss_feed/test_poller.py
  - tests/rss_feed/test_feed_writer.py
  - tests/rss_feed/test_server.py
  - tests/rss_feed/test_integration.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "RSS feeds are fetched on a configurable poll interval and new entries are detected via dedup"
    - "Each entry is classified as FULL_ARTICLE, STUB, LINK_LIST, or DISCARD via content heuristics"
    - "STUB entries are enriched through a 4-stage fallback chain (trafilatura, readability, Playwright, Wayback)"
    - "LINK_LIST entries have their child links extracted, deduped, and individually enriched"
    - "Output RSS XML files are atomically written and served via HTTP for Readwise Reader"
    - "Cross-feed content-hash deduplication prevents duplicate articles across feeds"
    - "Config is hot-reloadable each poll cycle with fallback to last-good config on parse error"
  artifacts:
    - path: src/rss_feed/config.py
      provides: "AppConfig frozen dataclass tree, load_config with validation and reload fallback"
    - path: src/rss_feed/db.py
      provides: "SQLite database with seen_entries and feed_state tables, dedup queries"
    - path: src/rss_feed/classifier.py
      provides: "Heuristic classifier returning Classification enum for RSS entry content"
    - path: src/rss_feed/enricher.py
      provides: "4-stage extraction fallback chain with per-domain rate limiting"
    - path: src/rss_feed/poller.py
      provides: "Feed processing orchestrator: fetch, classify, enrich, store, write XML"
    - path: src/rss_feed/feed_writer.py
      provides: "Atomic RSS XML file generation via python-feedgen"
    - path: src/rss_feed/server.py
      provides: "HTTP server restricted to /feeds/*.xml paths"
    - path: src/rss_feed/main.py
      provides: "Main loop with poll timer, server thread, graceful shutdown"
  key_links:
    - from: src/rss_feed/poller.py
      to: src/rss_feed/classifier.py
      via: "classify() call per entry"
      pattern: function-call
    - from: src/rss_feed/poller.py
      to: src/rss_feed/enricher.py
      via: "enrich_url() call for STUB and LINK_LIST entries"
      pattern: function-call
    - from: src/rss_feed/poller.py
      to: src/rss_feed/feed_writer.py
      via: "write_feed() to regenerate output XML after processing"
      pattern: function-call
    - from: src/rss_feed/main.py
      to: src/rss_feed/poller.py
      via: "process_feed() called in poll loop per configured feed"
      pattern: function-call
    - from: src/rss_feed/main.py
      to: src/rss_feed/server.py
      via: "create_server() started in daemon thread"
      pattern: function-call
---

# RSS Feed Enrichment Pipeline — Implementation Plan

## Objective

Build a local RSS feed enrichment pipeline as a new `src/rss_feed` package in this monorepo. The pipeline classifies, enriches, and re-serves RSS feeds for Readwise Reader consumption.

Readwise Reader receives cleaned, full-content RSS feeds instead of truncated stubs or link-list digests. The pipeline runs as a single Python process with a timed poll loop and a static-file HTTP server.

**Output:** Complete `src/rss_feed/` package with 9 modules, `config.yaml`, updated `pyproject.toml`, and full test suite in `tests/rss_feed/`.

## Execution Context

This is a new package alongside `src/langgraph_agents` in an existing monorepo. The project uses uv for dependency management, hatchling as build backend, and pytest for testing. Python 3.13 locally, requires 3.11+.

Existing pyproject.toml uses hatchling build backend with `packages = ["src/langgraph_agents"]`. The rss_feed package will be added as a second entry in that list. Dependencies are managed via `[project.optional-dependencies]` with an `rss` extra group.

**Constraint:** Do not modify any files under `src/langgraph_agents/` or existing `tests/test_*.py` files.

---

## Task 1: Project Scaffold, Config Module, and Database Layer

**Files:** pyproject.toml, .gitignore, config.yaml, src/rss_feed/__init__.py, src/rss_feed/config.py, src/rss_feed/db.py, tests/rss_feed/__init__.py, tests/rss_feed/conftest.py, tests/rss_feed/test_config.py, tests/rss_feed/test_db.py

This task establishes the package skeleton, dependency configuration, and the two foundational modules that all downstream modules depend on.

### Scaffold

- Edit pyproject.toml: add `[project.optional-dependencies]` section with `rss = ["feedparser>=6.0", "httpx>=0.27", "trafilatura>=1.0", "readability-lxml>=0.8", "playwright>=1.40", "python-feedgen>=1.0", "pyyaml>=6.0"]`. Add `"src/rss_feed"` to `tool.hatch.build.targets.wheel.packages` list. Add `pythonpath = ["src"]` to `tool.pytest.ini_options`.
- Edit .gitignore: append `data/` line.
- Create src/rss_feed/__init__.py with module docstring: "RSS feed enrichment pipeline."
- Create config.yaml with all sections: poll_interval (int, minutes, default 15), server_port (int, default 8778), feeds (list of name/url dicts with 2 example feeds), discard_patterns (list of regex strings for twitter, instagram, tiktok, reddit URLs), classification (min_full_article_length: 500, link_list_min_links: 5, link_list_max_text_ratio: 0.3), enrichment (fetch_timeout: 30, wayback_enabled: true, max_links_per_entry: 25, min_extraction_length: 200), rate_limit (per_domain_delay: 2.0), output (max_items_per_feed: 50).
- Run `uv sync --extra rss` then `uv run playwright install chromium`.

### Config Module (TDD)

- Frozen dataclasses: FeedConfig(name, url), ClassificationConfig(min_full_article_length, link_list_min_links, link_list_max_text_ratio), EnrichmentConfig(fetch_timeout, wayback_enabled, max_links_per_entry, min_extraction_length), RateLimitConfig(per_domain_delay), OutputConfig(max_items_per_feed), AppConfig(poll_interval, server_port, feeds, discard_patterns, classification, enrichment, rate_limit, output).
- load_config(path, fallback=None) -> AppConfig: parse YAML, validate, return. On failure: return fallback if provided, else raise ConfigError.
- Validation: feeds list non-empty, feed names match `^[a-zA-Z0-9_-]+$`, discard patterns compile as regex, numeric fields positive.
- Write tests FIRST: test_loads_valid_config, test_rejects_invalid_feed_name, test_rejects_empty_feeds, test_missing_file_raises, test_invalid_yaml_raises, test_discard_patterns_compile, test_reload_fallback.
- conftest.py: tmp_config fixture that writes minimal valid config.yaml to tmp_path, accepts overrides dict with deep-merge.

### Database Module (TDD)

- EntryRow dataclass with fields: feed_name, entry_id, url, title, author, host, classification, extraction_method, content_html, content_length, original_content_length, content_hash, link_count, parent_entry_id, published_date, fetch_status.
- Database(path) class wrapping sqlite3.connect with WAL mode, auto-creates schema on init.
- Tables: seen_entries (PK: feed_name + entry_id, indexed on host, url, content_hash), feed_state (PK: feed_name, stores etag, last_modified, last_poll).
- Methods: insert_entry, is_seen, content_hash_exists, upsert_feed_state, get_feed_state, recent_entries, content_hash_first_feed, close.
- Write tests FIRST: test_insert_and_check_seen, test_duplicate_entry_skipped, test_content_hash_exists, test_feed_state_round_trip, test_feed_state_missing, test_recent_entries, test_content_hash_first_feed.

### Verification

```
uv sync --extra rss && uv run python -c "import rss_feed" && uv run pytest tests/rss_feed/test_config.py tests/rss_feed/test_db.py -v --tb=short
```

**Done when:** Package imports successfully. All 14 config and database tests pass. config.yaml parses with all required sections. SQLite DB creates schema and handles all CRUD operations.

---

## Task 2: Classifier Module

**Files:** src/rss_feed/classifier.py, tests/rss_feed/test_classifier.py

Implement heuristic classification of RSS entry content into four categories.

### Implementation

- Classification enum with values: FULL_ARTICLE, STUB, LINK_LIST, DISCARD.
- classify(html_content, url, discard_patterns, cfg) -> Classification:
  1. Check URL against each pattern in discard_patterns. Any match returns DISCARD.
  2. Parse HTML with internal _LinkTextParser(HTMLParser) that splits text into anchor-text and non-anchor-text buckets.
  3. Count anchor tags. If count >= cfg.link_list_min_links AND (non-anchor-text-length / total-text-length) is below cfg.link_list_max_text_ratio, return LINK_LIST.
  4. Check for truncation markers: "...", "[...]", "read more", "continue reading" (case-insensitive). If found, return STUB.
  5. If total stripped text length is below cfg.min_full_article_length, return STUB.
  6. Otherwise return FULL_ARTICLE.
- _LinkTextParser: subclass html.parser.HTMLParser. Track whether inside an anchor tag. Accumulate text in two lists (anchor_texts, other_texts). Expose anchor_text_length and other_text_length properties.

### Tests (write first)

- test_full_article: 1000-char paragraph with no links classifies as FULL_ARTICLE.
- test_stub_short_content: 50-char text classifies as STUB.
- test_stub_truncation_marker: text with "Read more" at end classifies as STUB.
- test_link_list: HTML with 10 anchor tags and minimal non-anchor text classifies as LINK_LIST.
- test_discard_by_url: URL matching twitter pattern returns DISCARD regardless of content length.
- test_link_list_needs_minimum: HTML with only 2 links (below threshold) does NOT classify as LINK_LIST.

### Verification

```
uv run pytest tests/rss_feed/test_classifier.py -v --tb=short
```

**Done when:** All 6 classifier tests pass. Classification enum has 4 values. _LinkTextParser correctly separates anchor vs non-anchor text.

---

## Task 3: Enricher Module

**Files:** src/rss_feed/enricher.py, tests/rss_feed/test_enricher.py

Implement the content extraction pipeline that tries progressively heavier methods to get full article text.

### Implementation

- EnrichmentResult dataclass: text, html, title, method, fetch_status, content_hash.
- enrich_url(url, cfg, rate_cfg) -> EnrichmentResult: Runs 4-stage fallback chain, returning on first success (text length >= cfg.min_extraction_length):
  1. httpx + trafilatura: fetch HTML via httpx.get with browser-like User-Agent. Extract with trafilatura. Check length.
  2. Same HTML + readability-lxml: run readability.Document(html).summary(), then trafilatura.extract on that. Check length.
  3. Playwright + trafilatura: only if Playwright available. Launch headless Chromium, navigate with networkidle wait. Extract with trafilatura. Check length.
  4. Wayback Machine + trafilatura: only if cfg.wayback_enabled. Query CDX API for latest snapshot. Fetch via web.archive.org. Extract with trafilatura. Check length.
  5. All failed: return EnrichmentResult with method="failed", fetch_status="all_methods_exhausted".
- Per-domain rate limiting: module-level dict tracking last request time per domain. Before each HTTP request, sleep if needed to respect rate_cfg.per_domain_delay.
- Content hash: sha256 of extracted text.
- Wrap Playwright import in try/except ImportError to gracefully degrade.

### Tests (write first, all external calls mocked)

- test_trafilatura_success: mock fetch returning good HTML, mock trafilatura returning 500-char text. Assert method="trafilatura".
- test_falls_back_to_readability: mock trafilatura returning 10-char text on first call, readability returning 500-char text. Assert method="readability".
- test_all_fallbacks_exhausted: mock all stages returning empty/short text. Assert method="failed".
- test_fetch_failure_records_status: mock fetch raising httpx.RequestError. Assert fetch_status contains the error.

### Verification

```
uv run pytest tests/rss_feed/test_enricher.py -v --tb=short
```

**Done when:** All 4 enricher tests pass. Fallback chain respects order. Rate limiter tracks per-domain timing. Graceful degradation when Playwright unavailable.

---

## Task 4: Feed Writer, HTTP Server, and Poller

**Files:** src/rss_feed/feed_writer.py, src/rss_feed/server.py, src/rss_feed/poller.py, tests/rss_feed/test_feed_writer.py, tests/rss_feed/test_server.py, tests/rss_feed/test_poller.py

Implement the three remaining modules that connect the pipeline: output generation, HTTP serving, and the orchestrator.

### Feed Writer (TDD)

- write_feed(feed_name, entries, output_dir, server_port) -> None:
  - Use python-feedgen: create FeedGenerator, set title/link/description.
  - For each entry dict: add FeedEntry with id, title, link, author, published, content (HTML).
  - Atomic write: write to NamedTemporaryFile then os.replace to final path.
- Tests: test_writes_valid_rss (feedparser.parse succeeds, correct item count), test_atomic_write (no .tmp files remain), test_empty_entries (valid RSS with 0 items).

### HTTP Server (TDD)

- create_server(feed_dir, port) -> HTTPServer:
  - Custom handler: only serve paths matching `/feeds/[a-zA-Z0-9_-]+\.xml`. Reject everything else with 404. No directory listings. Reject paths containing "..".
  - Return HTTPServer bound to given port. Use port=0 for tests.
- Tests: test_serves_existing_feed (200 with content), test_404_for_missing (404), test_404_for_non_feed_paths (404 for arbitrary paths). Use threading + httpx.

### Poller (TDD)

- process_feed(feed_cfg, app_cfg, db, output_dir) -> None:
  1. Conditional GET: use stored etag/last_modified from db. On 304, skip.
  2. Parse with feedparser.
  3. Per entry: skip if db.is_seen(). Get content HTML from entry.
  4. Classify via classify():
     - DISCARD: insert_entry with classification="discard", skip enrichment.
     - FULL_ARTICLE: compute content_hash, insert_entry with extraction_method="passthrough".
     - STUB: call enrich_url(). Insert_entry with enriched content.
     - LINK_LIST: extract all hrefs (up to max_links_per_entry). Insert parent entry. For each child link: check discard, check is_seen, enrich_url, insert with parent_entry_id set.
  5. Content-hash cross-feed dedup: exclude entries where content_hash_first_feed returns a different feed name.
  6. Get recent_entries, filter by dedup, call write_feed().
  7. Save feed_state with ETag and Last-Modified.
- Tests (mock httpx.get and enrich_url): test_processes_new_entry, test_skips_already_seen, test_link_list_expansion, test_content_hash_dedup.

### Verification

```
uv run pytest tests/rss_feed/test_feed_writer.py tests/rss_feed/test_server.py tests/rss_feed/test_poller.py -v --tb=short
```

**Done when:** All 10 tests pass (3 feed writer + 3 server + 4 poller). Feed writer produces valid RSS with atomic writes. Server restricts paths. Poller orchestrates the full classify-enrich-store-write pipeline.

---

## Task 5: Main Entry Point, Integration Test, and Final Verification

**Files:** src/rss_feed/__main__.py, src/rss_feed/main.py, tests/rss_feed/test_integration.py

Wire everything together into a runnable application and validate end-to-end.

### Main Entry Point

- src/rss_feed/__main__.py: single line `from rss_feed.main import main; main()`.
- src/rss_feed/main.py main() function:
  1. Configure logging with INFO level.
  2. Load config from config.yaml.
  3. Test Playwright availability, log warning if ImportError.
  4. Create data dirs: data/ and data/feeds/.
  5. Init Database at data/rss_feed.db.
  6. Start server in daemon thread. Log port.
  7. Register shutdown event for SIGINT and SIGTERM.
  8. Poll loop: reload config with fallback, process each feed (catch and log errors per feed), wait on shutdown event with timeout=poll_interval*60.
  9. On exit: log shutdown, stop server, close db.

### Integration Test

- test_full_pipeline:
  1. Start a local HTTPServer serving a directory with a static RSS XML file. The RSS has two entries: one full-article (500+ chars) and one stub (50 chars with "Read more..." marker).
  2. Create tmp_config pointing at the local feed. Set wayback_enabled=false.
  3. Init Database in tmp_path. Create output_dir.
  4. Call process_feed (NOT the full main loop).
  5. Assert: is_seen returns True for both entries. Output XML exists. feedparser.parse has at least 1 item.
  6. Call process_feed again. Assert entry count unchanged (dedup works).

### Final Verification

Run full test suite:

```
uv run pytest tests/rss_feed/ -v --tb=short
```

Smoke test: `uv run python -m rss_feed` with real config.yaml. Verify startup logs and clean Ctrl+C shutdown.

**Done when:** All 35 tests pass (14 config/db + 6 classifier + 4 enricher + 10 writer/server/poller + 1 integration). Application starts via `python -m rss_feed`, logs startup messages, and shuts down cleanly on SIGINT.

---

## Overall Verification Strategy

Each task uses TDD: tests are written first and confirmed failing, then implementation is written until all tests pass. The integration test validates the full pipeline end-to-end with a real RSS feed served locally.

Test commands by task:
- Task 1: `uv run pytest tests/rss_feed/test_config.py tests/rss_feed/test_db.py -v`
- Task 2: `uv run pytest tests/rss_feed/test_classifier.py -v`
- Task 3: `uv run pytest tests/rss_feed/test_enricher.py -v`
- Task 4: `uv run pytest tests/rss_feed/test_feed_writer.py tests/rss_feed/test_server.py tests/rss_feed/test_poller.py -v`
- Task 5: `uv run pytest tests/rss_feed/ -v` (full suite)

## Success Criteria

1. `uv run python -c "import rss_feed"` succeeds
2. `uv run pytest tests/rss_feed/ -v --tb=short` shows all 35+ tests passing
3. `uv run python -m rss_feed` starts, logs HTTP server and poll loop, shuts down on Ctrl+C
4. Output XML files in data/feeds/ are valid RSS parseable by feedparser
5. No modifications to existing src/langgraph_agents/ or tests/test_*.py files
