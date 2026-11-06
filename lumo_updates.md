# Task: Dynamic Crawler Selection + Per-Tier Branch Scoping

## Project Context

I'm building a universal multi-crawler web scraper pipeline in Python (asyncio + aiohttp).
Current architecture:

- **main.py** — CLI entry point (`argparse`) + interactive menu hub. Defines `PROFILE_CHOICES`
  (auto, hierarchical, flat_paged, asset_index, sitemap, feed, headless, infinite_scroll,
  authenticated, openapi, universal) and calls `ScraperDispatcher.run(target_url,
  forced_profile=..., keyword_filter=...)`.
- **utils/dispatch.py** — `ScraperDispatcher(max_concurrent=N)` that picks/forces a crawler
  profile and runs it.
- **base.py** — `BaseCrawler` shared parent class with: `log_discovery()`,
  `_sanitize_url()`, `_get_relative_path()`, `_matches_keyword()`,
  `_prompt_branch_selection(discovered_branches)` (already renders an interactive numbered
  menu after Tier 1 discovery and returns the selected branch list), and temp-file helpers.
- **downloader.py** — `UniversalDownloader` with semaphore-bounded async `download_batch()`,
  retry/backoff, and local caching to `DATA_DIR`.

## Feature 1: Dynamic Crawler/Profile Selection

Replace the current "one forced profile" flow with intelligent dynamic selection:

1. **Auto-probing phase:** Before committing to a crawler, run lightweight probe checks on the
   target (fetch homepage once, inspect response HTML + headers):
   - `sitemap.xml` / `robots.txt` present and parseable → candidate `sitemap`
   - RSS/Atom feeds (`<rss>`, `<feed>`, `application/rss+xml` link tags) → candidate `feed`
   - OpenAPI spec (`/openapi.json`, `/swagger.json`, `openapi.yaml`) → candidate `openapi`
   - Infinite scroll signals (JS-heavy SPA markers, `<script>` bundles like React/Vue/Next,
     pagination via API calls) → candidate `infinite_scroll`
   - Login form detected (`<form>` with `type="password"`) → candidate `authenticated`
   - Many asset/link-rich pages with shallow depth → `hierarchical`
   - Flat paginated listing (`?page=`, `/page/2`) → `flat_paged`
   - Image/asset index directories → `asset_index`
2. **Present the candidates** to the user as a ranked numbered menu with a confidence score
   and reason for each (e.g., "sitemap — robots.txt lists 2 sitemaps"), plus:
   - `[0]` or Enter = run the top-ranked candidate (recommended)
   - `[a]` = run ALL applicable crawlers in parallel/resequence
   - `[n]` = pick a specific profile manually (then show PROFILE_CHOICES)
3. **Multi-crawler support:** `ScraperDispatcher.run()` must accept and manage a *list* of
   profiles, running them sequentially (or concurrently where safe), deduplicating discovered
   URLs and downloaded files across crawlers (shared seen-set keyed on sanitized absolute URL).
4. Add `--profile auto` as the default behavior, and a `--non-interactive` /
   `--yes` flag that skips all prompts and takes the recommended choice (for cron use).

## Feature 2: Interactive Branch Selection at EVERY Tier

Currently `_prompt_branch_selection()` only fires once after Tier 1 discovery. Change this so
that at **each traversal tier** the crawler:

1. Collects the discovered subdirectory/branch URLs beneath the current level (a "branch" =
   distinct first-level path segment group under the current page, e.g. under `/archive/` the
   branches might be `/archive/2023/`, `/archive/2024/`, `/archive/press/`).
2. Before *crawling into* any branch, pause and show the existing numbered menu showing ALL
   discovered branches for that tier (raise the 15-item display cap or paginate it), plus
   `[0]` = all branches, `[s]` = skip this tier's prompt (crawl all remaining tiers without
   asking again), `[q]` = abort the crawl gracefully (finish pending downloads, then exit).
3. Only enqueue the selected branch URLs for discovery/download. Unselected branches are
   recorded but ignored (keep a summary at the end: "Skipped N branches").
4. Make this configurable: `--branch-prompt {all,first,every,none}` where
   - `all` = old behavior, prompt once after full Tier 1 discovery
   - `first` = prompt once per crawl start (default)
   - `every` = prompt at every tier (new requirement)
   - `none` = no prompting
5. Guard for non-interactive contexts: if stdin is not a TTY or `--non-interactive` is set,
   auto-select all branches instead of blocking on `input()`. Wrap the `input()` calls to
   catch `EOFError`/`KeyboardInterrupt` and treat them as "abort/return []" rather than
   crashing.

## Constraints & Quality Requirements

- Python 3.11+, type hints everywhere, no new heavy dependencies (aiohttp, yarl, bs4, tqdm
  already in use — lxml optional).
- All crawlers inherit from `BaseCrawler`; implement the tier-selection logic ONCE in
  `BaseCrawler` (e.g., `async def select_branches(self, tier_urls, tier_num)`) so every
  crawler profile inherits the behavior — do not duplicate menu code per profile.
- Keep the async downloader untouched except for accepting the filtered URL list.
- Preserve existing behavior when `--branch-prompt first` (backwards compatible).
- Probe requests must respect the same polite delay/timeout settings as the downloader.
- Handle edge cases: empty branch lists (skip prompt), duplicate branches, branches whose
  path prefixes overlap (e.g. selecting `/a/` implicitly covers `/a/b/` — dedupe).

## Deliverables

1. Updated `utils/dispatch.py` — probe engine + candidate ranking + multi-profile runner.
2. Updated `base.py` — reusable async tier-branch selection method with pagination and
   non-TTY fallback.
3. Updated `main.py` — new/changed CLI flags wired through, help text updated.
4. Brief summary of each crawler profile module needing the per-tier hook call added
   (one line where `select_branches()` should be awaited in its traversal loop).
