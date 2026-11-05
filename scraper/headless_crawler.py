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

class HeadlessCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler utilizing headless browser automation (Playwright) 
        to render Single Page Applications (SPAs), dynamic JavaScript DOMs, and keyword filtering.
        """
        super().__init__(name="HeadlessCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()
        self.visited_assets = set()

    async def crawl_async(self, start_url: str):
        if not PLAYWRIGHT_AVAILABLE:
            print("[!] Playwright is not installed.")
            print("[!] Please run: pip install playwright && playwright install chromium")
            return

        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] HeadlessCrawler active (Playwright SPA Engine) for: {sanitized_start}")
        print(f"[*] Scope Locked -> Host: {allowed_netloc}")

        urls_to_visit = [sanitized_start]
        all_download_items = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            while urls_to_visit:
                current_url = urls_to_visit.pop(0)
                clean_current = self._sanitize_url(current_url)
                
                if clean_current in self.visited_urls or ScrapingRules.is_high_risk_url(clean_current):
                    continue
                
                self.visited_urls.add(clean_current)
                print(f"[*] Rendering via Headless Browser: {clean_current}")

                try:
                    # Navigate and wait for dynamic network rendering
                    await page.goto(clean_current, wait_until="networkidle", timeout=30000)
                    
                    # Simulate slight scroll to trigger lazy-loaded elements / infinite layouts
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1.5)

                    content = await page.content()
                    
                    # Inspect keyword filter
                    has_keyword = self._matches_keyword(content)

                    # Queue current rendered page for saving
                    rel_path = self._get_relative_path(sanitized_start, clean_current)
                    
                    # Extract links using HTMLDocumentParser
                    nav_links, asset_urls = HTMLDocumentParser.extract_links_and_assets(
                        content, clean_current, allowed_netloc, allowed_base_path
                    )

                    child_links_found = len(nav_links)

                    for clean_target in nav_links:
                        if clean_target not in self.visited_urls and clean_target not in urls_to_visit:
                            urls_to_visit.append(clean_target)
                            self.log_discovery(clean_target, item_type="page")

                    for clean_asset in asset_urls:
                        if clean_asset not in self.visited_assets:
                            self.visited_assets.add(clean_asset)
                            target_rel = self._get_relative_path(sanitized_start, clean_asset)
                            all_download_items.append((clean_asset, target_rel))
                            self.log_discovery(clean_asset, item_type="asset")

                    if not self.keyword_filter or has_keyword or child_links_found > 0:
                        if (clean_current, rel_path) not in all_download_items:
                            if not (self.keyword_filter and child_links_found == 0 and not has_keyword):
                                all_download_items.append((clean_current, rel_path))

                except Exception as e:
                    print(f"    [!] Error rendering headless page {current_url}: {e}")

            await browser.close()

        print(f"\n[*] Headless discovery complete! Total items queued: {len(all_download_items)}")

        # High-speed batch download via UniversalDownloader
        batch_size = 200
        for i in range(0, len(all_download_items), batch_size):
            batch = all_download_items[i:i + batch_size]
            print(f"[*] Downloading headless batch {i // batch_size + 1} ({len(batch)} files)...")
            await self.downloader.download_batch(batch)

        print("[*] Headless crawl and download complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
