# Universal Scraper Pipeline Hub — Development Roadmap

## Phase 1: Robust Probing & Architectural Fingerprinting (`config/rules.py`)
* **Objective:** Expand the probe phase to perform deep inspection of response headers, status codes, and structural text without hardcoding domains.
* **Key Tasks:**
  * Implement checks for security challenge markers (Cloudflare, CAPTCHAs) and authentication/paywall indicators (`401`, `403`, login forms).
  * Detect API-first payloads (`application/json`, OpenAPI endpoints, GraphQL schemas) alongside traditional HTML structures.
  * Assign confidence scores and descriptive reasons to candidate profiles (e.g., `sitemap`, `feed`, `infinite_scroll`, `headless`, `asset_index`, `flat_paged`, `hierarchical`).
  * Integrate content stabilization metrics for infinite-scroll targets (tracking document height changes rather than enforcing a rigid low iteration cap like 25).

## Phase 2: Multi-Crawler Swarm Dispatcher & Deduplication (`utils/dispatch.py`)
* **Objective:** Transition from a single-profile runner to an intelligent multi-crawler manager that coordinates parallel execution.
* **Key Tasks:**
  * Build the candidate selection menu logic that presents ranked profiles with confidence scores and user choices (`[0]` for recommended top choice, `[a]` for all applicable, `[n]` for manual override).
  * Update `ScraperDispatcher.run()` to manage a list of profiles.
  * Establish a shared, thread-safe seen-set (keyed on sanitized absolute URLs) across all concurrent crawler engines to prevent duplicate downloads and overlapping network requests.

## Phase 3: Universal Per-Tier Branch Scoping (`base.py`)
* **Objective:** Elevate branch filtering from a one-time Tier 1 prompt to an intelligent, reusable tier-by-tier governance model.
* **Key Tasks:**
  * Implement `select_branches()` inside `BaseCrawler` so every crawler profile inherits it automatically.
  * Design the interactive tier menu with pagination support, path grouping, and prefix deduplication (e.g., ensuring parent selections cover nested paths).
  * Add control options: `[0]` (all branches), `[s]` (skip remaining tier prompts), and `[q]` (graceful abort finishing pending downloads).
  * Implement safe non-TTY fallbacks, environment guards (`--non-interactive`), and exception handling (`EOFError`, `KeyboardInterrupt`).

## Phase 4: CLI Integration & Parameter Wiring (`main.py`)
* **Objective:** Expose the new capabilities cleanly through command-line arguments and interactive prompts.
* **Key Tasks:**
  * Wire up `--profile auto` as the default behavior.
  * Add `--branch-prompt {all,first,every,none}` to control scoping granularity.
  * Add `--yes` / `--non-interactive` flags to bypass interactive menus for automated cron or batch operations.
