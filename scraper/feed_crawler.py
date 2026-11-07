import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from yarl import URL
from tqdm import tqdm
from config import ScrapingRules
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

class FeedCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler for RSS, Atom, or JSON feeds to harvest 
        articles and publication attachments chronologically with keyword filtering.
        """
        super().__init__(name="FeedCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        
        # Initialize default request headers using case-insensitive mapping
        self.default_headers["Accept"] = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        parsed_base = URL(sanitized_start)
        
        print(f"[*] FeedCrawler active. Probing feeds for: {sanitized_start}")
        
        # Step 1: Probe start page to locate alternate RSS/Atom feed links
        results = await self.downloader.download_batch([(sanitized_start, "probe_feed.html")])
        feed_urls = []
        
        for url, saved_file in results:
            if saved_file and saved_file.exists():
                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    soup = BeautifulSoup(content, "lxml")
                    
                    for link in soup.find_all("link", rel="alternate"):
                        link_type = link.get("type", "").lower()
                        if "rss" in link_type or "atom" in link_type or "xml" in link_type:
                            href = link.get("href")
                            if href:
                                abs_feed = str(URL(url).join(URL(href)))
                                if abs_feed not in feed_urls:
                                    feed_urls.append(abs_feed)
                except Exception as e:
                    print(f"    [!] Error detecting feed links: {e}")

        # Fallback to standard common feed endpoints if none discovered in DOM
        if not feed_urls:
            feed_urls = [
                str(parsed_base.with_path("/feed/")),
                str(parsed_base.with_path("/rss.xml")),
                str(parsed_base.with_path("/atom.xml"))
            ]

        print(f"[*] Investigating {len(feed_urls)} potential feed endpoints...")
        
        feed_results = await self.downloader.download_batch([(f, "temp_feed.xml") for f in feed_urls])
        article_urls = []

        for f_url, saved_file in feed_results:
            if saved_file and saved_file.exists() and saved_file.stat().st_size > 0:
                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    soup = BeautifulSoup(content, "lxml-xml")
                    
                    # Support both RSS <item> and Atom <entry>
                    items = soup.find_all("item") or soup.find_all("entry")
                    for item in items:
                        # Extract entry text/description/summary for keyword checking
                        item_text = item.get_text()
                        if not self._matches_keyword(item_text):
                            continue

                        link_tag = item.find("link")
                        target = None
                        if link_tag:
                            target = link_tag.get("href") or link_tag.get_text()
                        
                        if target:
                            clean_target = self._sanitize_url(target.strip())
                            if clean_target and not ScrapingRules.is_high_risk_url(clean_target):
                                if clean_target not in article_urls:
                                    article_urls.append(clean_target)
                                    self.log_discovery(clean_target, item_type="page")
                except Exception as e:
                    print(f"    [!] Error parsing feed XML {f_url}: {e}")

        if not article_urls:
            print("    [!] No entries matched the criteria in feeds.")
            return

        print(f"[*] Harvested {len(article_urls)} entries from feeds. Downloading items...")
        
        all_download_items = [(u, self._get_relative_path(sanitized_start, u)) for u in article_urls]
        
        batch_size = 200
        for i in range(0, len(all_download_items), batch_size):
            batch = all_download_items[i:i + batch_size]
            print(f"[*] Downloading feed article batch {i // batch_size + 1} ({len(batch)} files)...")
            await self.downloader.download_batch(batch)

        print("[*] Feed crawling and harvesting complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
