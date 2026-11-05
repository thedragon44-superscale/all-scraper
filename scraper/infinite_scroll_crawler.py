import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from yarl import URL
from tqdm import tqdm
from config import ScrapingRules
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class InfiniteScrollCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler that simulates automated vertical scrolling actions 
        to trigger lazy-loading and harvest content from infinite-scroll feeds with keyword filtering.
        """
        super().__init__(name="InfiniteScrollCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()
        self.visited_assets = set()

    async def crawl_async(self, start_url: str, max_scrolls: int = 25):
        if not PLAYWRIGHT_AVAILABLE:
            print("[!] Playwright is required for InfiniteScrollCrawler.")
            print("[!] Please run: pip install playwright && playwright install chromium")
            return

        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] InfiniteScrollCrawler active for: {sanitized_start}")
        print(f"[*] Max scroll iterations cap: {max_scrolls}")

        all_download_items = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_context().new_page()

            print(f"[*] Navigating to infinite scroll feed target...")
            await page.goto(sanitized_start, wait_until="networkidle", timeout=30000)

            last_height = await page.evaluate("document.body.scrollHeight")
            scroll_count = 0

            while scroll_count < max_scrolls:
                scroll_count += 1
                print(f"[*] Executing scroll iteration [{scroll_count}/{max_scrolls}]...")
                
                # Scroll to bottom of the viewport
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for content to render / network to settle
                try:
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    print("[*] Scroll height stabilized. Reached the end of the infinite feed.")
                    break
                last_height = new_height

            # Capture fully expanded DOM content
            content = await page.content()
            await browser.close()

        # Queue start page
        has_keyword = self._matches_keyword(content)
        start_rel = self._get_relative_path(sanitized_start, sanitized_start)
        
        # Extract links using HTMLDocumentParser
        nav_links, asset_urls = HTMLDocumentParser.extract_links_and_assets(
            content, sanitized_start, allowed_netloc, allowed_base_path
        )

        child_links_found = len(nav_links)

        for clean_target in nav_links:
            if clean_target not in self.visited_urls:
                self.visited_urls.add(clean_target)
                target_rel = self._get_relative_path(sanitized_start, clean_target)
                all_download_items.append((clean_target, target_rel))
                self.log_discovery(clean_target, item_type="page")

        for clean_asset in asset_urls:
            if clean_asset not in self.visited_assets:
                self.visited_assets.add(clean_asset)
                target_rel = self._get_relative_path(sanitized_start, clean_asset)
                all_download_items.append((clean_asset, target_rel))
                self.log_discovery(clean_asset, item_type="asset")

        if not self.keyword_filter or has_keyword or child_links_found > 0:
            if not (self.keyword_filter and child_links_found == 0 and not has_keyword):
                all_download_items.append((sanitized_start, start_rel))

        print(f"\n[*] Infinite scroll collection complete! Total items queued: {len(all_download_items)}")

        # Chunked batch downloading
        batch_size = 200
        for i in range(0, len(all_download_items), batch_size):
            batch = all_download_items[i:i + batch_size]
            print(f"[*] Downloading scroll batch {i // batch_size + 1} ({len(batch)} files)...")
            await self.downloader.download_batch(batch)

        print("[*] Infinite scroll crawl and download complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
