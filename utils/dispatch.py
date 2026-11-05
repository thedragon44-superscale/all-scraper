import asyncio
from yarl import URL
from bs4 import BeautifulSoup
from config import ScrapingRules
from scraper.downloader import UniversalDownloader
from scraper import (
    HierarchicalCrawler, 
    FlatCrawler, 
    AssetCrawler, 
    SitemapCrawler, 
    FeedCrawler, 
    HeadlessCrawler, 
    InfiniteScrollCrawler, 
    AuthenticatedCrawler, 
    OpenApiSwaggerCrawler, 
    UniversalCrawler
)

class ScraperDispatcher:
    """
    Orchestration utility that probes a target URL, fingerprints its 
    architecture using rules, and dynamically dispatches multi-crawler pipelines.
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)

    async def probe_and_route(self, start_url: str, forced_profile: str = None, keyword_filter: str = None):
        """
        Performs a lightweight Tier 1 probe to analyze site structure,
        or respects a user-forced crawler profile override.
        """
        sanitized_start = str(URL(start_url))
        print(f"[*] Dispatcher probing target: {sanitized_start}")

        if forced_profile:
            print(f"[*] User override active. Forcing profile: '{forced_profile}'")
            profiles = [forced_profile]
        else:
            # Step 1: Perform lightweight probe of Tier 1 links and capture raw HTML
            sample_urls, raw_html = await self._fetch_tier_one_samples(sanitized_start)
            
            # Step 2: Fingerprint architecture using rules utility with sample URLs and raw HTML
            primary_profile = ScrapingRules.fingerprint_architecture(sample_urls, raw_html)
            print(f"[*] Architectural fingerprint detected: '{primary_profile}'")
            
            # Build active profile execution list (e.g., primary crawler + companion asset sweep)
            profiles = [primary_profile]
            
            # Companion logic: If scraping a content site, automatically bundle an asset check
            if primary_profile in ["hierarchical", "flat_paged", "feed", "sitemap"] and "asset_index" not in profiles:
                profiles.append("asset_index")

        # Step 3: Execute multi-crawler dispatch pipeline
        await self._dispatch_to_crawlers(profiles, sanitized_start, keyword_filter=keyword_filter)

    async def _fetch_tier_one_samples(self, start_url: str) -> tuple[list[str], str]:
        """Fetches the start URL, extracts sample child links, and returns raw HTML content for fingerprinting."""
        sample_urls = []
        raw_html = ""
        try:
            results = await self.downloader.download_batch([(start_url, "probe_index.html")])
            for url, saved_file in results:
                if saved_file and saved_file.exists() and saved_file.suffix.lower() == ".html":
                    raw_html = saved_file.read_text(encoding="utf-8", errors="ignore")
                    soup = BeautifulSoup(raw_html, "lxml")
                    allowed_netloc = URL(start_url).host
                    
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"].strip()
                        if not href or href.startswith("javascript:") or href.startswith("#"):
                            continue
                        absolute_url = URL(start_url).join(URL(href))
                        clean_target = str(absolute_url)
                        
                        if URL(clean_target).host == allowed_netloc:
                            if clean_target not in sample_urls:
                                sample_urls.append(clean_target)
        except Exception as e:
            print(f"    [!] Warning during probe phase: {e}")
            
        return sample_urls, raw_html

    async def _dispatch_to_crawlers(self, profiles: list[str], start_url: str, keyword_filter: str = None):
        """Delegates execution to one or more specialized crawlers concurrently with optional keyword filtering."""
        print(f"[*] Dispatching active crawler engines: {profiles}")
        
        tasks = []
        for profile in profiles:
            if profile == "flat_paged":
                crawler = FlatCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "asset_index":
                crawler = AssetCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "sitemap":
                crawler = SitemapCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "feed":
                crawler = FeedCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "headless":
                crawler = HeadlessCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "infinite_scroll":
                crawler = InfiniteScrollCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "authenticated":
                crawler = AuthenticatedCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "openapi":
                crawler = OpenApiSwaggerCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            elif profile == "hierarchical":
                crawler = HierarchicalCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                tasks.append(crawler.crawl_async(start_url))
            else:
                crawler = UniversalCrawler(max_concurrent=self.max_concurrent, keyword_filter=keyword_filter)
                if hasattr(crawler, "crawl_async"):
                    tasks.append(crawler.crawl_async(start_url))
                else:
                    tasks.append(asyncio.to_thread(crawler.crawl, start_url))

        # Run multiple crawlers concurrently
        await asyncio.gather(*tasks)
        print("[*] All dispatched crawler pipelines completed execution.")

    def run(self, start_url: str, forced_profile: str = None, keyword_filter: str = None):
        """Synchronous wrapper for dispatch execution."""
        asyncio.run(self.probe_and_route(start_url, forced_profile, keyword_filter=keyword_filter))
