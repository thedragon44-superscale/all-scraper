import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from yarl import URL
from tqdm import tqdm
from config import ScrapingRules
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

class SitemapCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler that parses sitemap.xml to instantly harvest 
        and download all indexed URLs without recursive UI traversal with keyword filtering.
        """
        super().__init__(name="SitemapCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        parsed_base = URL(sanitized_start)
        
        # Target standard sitemap.xml location at root domain/path
        sitemap_url = str(parsed_base.with_path("/sitemap.xml"))
        print(f"[*] SitemapCrawler active. Probing sitemap: {sitemap_url}")
        
        results = await self.downloader.download_batch([(sitemap_url, "sitemap.xml")])
        urls_to_crawl = []
        
        for url, saved_file in results:
            if saved_file and saved_file.exists():
                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    
                    # Evaluate keyword filter against sitemap content if active
                    if not self._matches_keyword(content):
                        continue

                    # Use lxml-xml parser to parse sitemap XML structure
                    soup = BeautifulSoup(content, "lxml-xml")
                    loc_tags = soup.find_all("loc")
                    
                    for loc in loc_tags:
                        target_url = loc.get_text().strip()
                        clean_target = self._sanitize_url(target_url)
                        
                        if clean_target and not ScrapingRules.is_high_risk_url(clean_target):
                            if URL(clean_target).host == parsed_base.host:
                                if clean_target not in urls_to_crawl:
                                    urls_to_crawl.append(clean_target)
                                    self.log_discovery(clean_target, item_type="page")
                except Exception as e:
                    print(f"    [!] Error parsing sitemap XML: {e}")

        if not urls_to_crawl:
            print("    [!] No URLs matched the criteria in sitemap.xml. Falling back to base URL.")
            urls_to_crawl = [sanitized_start]

        print(f"[*] Successfully extracted {len(urls_to_crawl)} filtered URLs from sitemap.")

        # Build download queue items
        all_download_items = [(u, self._get_relative_path(sanitized_start, u)) for u in urls_to_crawl]

        # Chunked batch downloading with progress
        batch_size = 200
        for i in range(0, len(all_download_items), batch_size):
            batch = all_download_items[i:i + batch_size]
            print(f"[*] Downloading sitemap batch {i // batch_size + 1} ({len(batch)} files)...")
            await self.downloader.download_batch(batch)

        print("[*] Sitemap crawl and download complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
