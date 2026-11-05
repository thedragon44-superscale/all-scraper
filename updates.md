# Scraper Architecture Refactoring & Multi-Core Roadmap

This document outlines completed infrastructure upgrades, the newly integrated **Multi-Core Multiprocessing Parsing Engine**, and detailed specifications for bringing the remaining specialized crawlers up to parity with our updated pipeline standards.

---

## Completed Architecture & Master Modules

| Module / File Path | Current Status | Key Enhancements |
| :--- | :--- | :--- |
| **`scraper/base.py`** | ✅ Complete | - `BaseCrawler` base class initialization<br>- Thread-safe hash-based temp file creation (`_create_temp_discovery_file`) and automatic cleanup (`_cleanup_temp_file`) to prevent disk bloat<br>- Text-content keyword filtering helper (`_matches_keyword`)<br>- Interactive branch menu prompt (`_prompt_branch_selection`) |
| **`parser/html_parser.py`** | ✅ Complete | - Decoupled DOM parsing (`BeautifulSoup` + `lxml`) from networking<br>- Strict `yarl` path sanitization and trailing-slash directory enforcement<br>- High-risk loop detection and target extension separation |
| **`parser/__init__.py`** | ✅ Complete | - Exposed `HTMLDocumentParser` alongside existing parsers |
| **`scraper/hierarchical_crawler.py`** | ✅ Complete | - Full `BaseCrawler` inheritance<br>- Integrated Tier 1 auto-sniffing and branch scoping<br>- Leaf-node text-content keyword inspection<br>- Temporary file unlink pattern during batch processing |
| **`scraper/crawler.py`** (`UniversalCrawler`) | ✅ Complete | - Full `BaseCrawler` inheritance<br>- Real-time streaming discovery logs<br>- Keyword content filtering and progress monitoring (`tqdm`) |
| **`utils/dispatch.py`** | ✅ Complete | - Passed optional `keyword_filter` down through `probe_and_route` and `_dispatch_to_crawlers` |
| **`main.py`** | ✅ Complete | - Added interactive prompt and CLI flag `--keyword` for target search phrases |

---

## New Architecture: Multi-Core Multiprocessing Parser Pool

To overcome Python's single-threaded event loop and GIL bottlenecks during massive document discovery phases (e.g., parsing hundreds of HTML files simultaneously on multi-core hardware like a Raspberry Pi 5), we introduce a **Process Pool Architecture**:

1. **Core Allocation (Pi 5 Optimization):**
   - **Core 1:** Dedicated to the main async event loop (`asyncio`), network I/O (`aiohttp` / `UniversalDownloader`), and live terminal progress updates (`tqdm`).
   - **Cores 2, 3, & 4:** Dedicated `ProcessPoolExecutor` worker processes running independent Python instances to strip away GIL overhead during CPU-bound DOM tree construction and text keyword inspection.
2. **Asynchronous Executor Bridging:**
   - Utilizing `loop.run_in_executor()` to allow the main async thread to cleanly `await` parallel process results without blocking network downloads or freezing terminal feedback.
3. **Pickle-Safe Workers:**
   - Leveraging pure static methods from `HTMLDocumentParser` (`matches_keyword`, `extract_links_and_assets`) that take and return clean, picklable string structures.

---

## Remaining Specialized Crawler Implementation Plan

Below is the complete file-by-file breakdown for updating the remaining specialized crawlers listed in the `scraper/` directory.

scraper/
├── asset_crawler.py
├── authenticated_crawler.py
├── feed_crawler.py
├── flat_crawler.py
├── headless_crawler.py
├── infinite_scroll_crawler.py
├── openapi_swagger_crawler.py
└── sitemap_crawler.py

### 1. `scraper/flat_crawler.py`
* **Target Architecture:** Paged/flat index navigation structures (e.g., `/page/1`, `/page/2`).
* **Required Behaviors:**
  - Inherit from `BaseCrawler` and invoke `super().__init__(name="FlatCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)`.
  - Replace direct DOM content inspection with in-memory parsing using `HTMLDocumentParser` and temporary hash files.
  - Apply `self._matches_keyword(content)` to individual article/item endpoints before queuing them for local storage.

### 2. `scraper/asset_crawler.py`
* **Target Architecture:** Media, PDF, and image index sweeps.
* **Required Behaviors:**
  - Inherit from `BaseCrawler` and invoke `super().__init__(name="AssetCrawler", ...)`.
  - Pass discovered asset URLs through `_sanitize_url` to prevent redundant downloads across query string variations.
  - Stream asset discovery using `self.log_discovery(clean_url, item_type="asset")`.

### 3. `scraper/sitemap_crawler.py`
* **Target Architecture:** XML Sitemaps (`sitemap.xml`, `sitemap_index.xml`).
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Fetch sitemap indexes and unpack nested target endpoints asynchronously.
  - Perform Tier 2 head-fetching/content inspection against `self._matches_keyword(content)` before enqueuing mapped URLs for final batch processing.

### 4. `scraper/feed_crawler.py`
* **Target Architecture:** RSS / Atom feed syndication endpoints (`/feed`, `/rss.xml`).
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Extract target post entry content and links from XML structures.
  - Match item summary/content against `self.keyword_filter` prior to queue insertion.

### 5. `scraper/headless_crawler.py`
* **Target Architecture:** Dynamic single-page applications (SPAs) requiring DOM execution.
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Pass rendered page DOM strings into `self._create_temp_discovery_file(content)` for parsing.
  - Ensure temporary rendering files are safely removed via `self._cleanup_temp_file(temp_path)`.

### 6. `scraper/infinite_scroll_crawler.py`
* **Target Architecture:** Dynamically loaded vertical feeds via virtual scroll listeners.
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Monitor DOM insertion cycles and execute keyword filtering against newly rendered post nodes prior to asset extraction.

### 7. `scraper/authenticated_crawler.py`
* **Target Architecture:** Cookie-backed or session-authenticated portal crawling.
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Preserve session state while leveraging shared URL sanitization and temp-file parsing for private document trees.

### 8. `scraper/openapi_swagger_crawler.py`
* **Target Architecture:** OpenAPI/Swagger JSON/YAML spec endpoints.
* **Required Behaviors:**
  - Inherit from `BaseCrawler`.
  - Parse API schemas to extract endpoint definitions and automatically map export paths.

---

## Standardized Integration Template (with Multi-Core Processing)

When refactoring each remaining crawler file, use the following structural pattern integrating `ProcessPoolExecutor`:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from yarl import URL
from tqdm import tqdm
from .base import BaseCrawler
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader

def _parse_worker(payload):
    url, content, base_url, netloc, base_path, keyword = payload
    has_keyword = HTMLDocumentParser.matches_keyword(content, keyword)
    links, assets = HTMLDocumentParser.extract_links_and_assets(content, base_url, netloc, base_path)
    return url, has_keyword, links, assets

class SpecificCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        super().__init__(
            name="SpecificCrawler", 
            max_concurrent=max_concurrent, 
            keyword_filter=keyword_filter
        )
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        # Main async loop handles downloads, offloads parsing to process pool across Cores 2-4
        
    def crawl(self, start_url: str):
        asyncio.run(self.crawl_async(start_url))
