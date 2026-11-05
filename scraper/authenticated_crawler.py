import asyncio
import getpass
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

class AuthenticatedCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler that automates login form submission, session 
        persistence, and crawling behind login-gated portals with keyword filtering.
        """
        super().__init__(name="AuthenticatedCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()
        self.visited_assets = set()

    async def crawl_async(self, start_url: str, login_url: str = None, username: str = None, password: str = None):
        if not PLAYWRIGHT_AVAILABLE:
            print("[!] Playwright is required for AuthenticatedCrawler.")
            print("[!] Please run: pip install playwright && playwright install chromium")
            return

        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] AuthenticatedCrawler active for target: {sanitized_start}")

        # Interactive credential prompt if not passed programmatically
        if not login_url:
            login_url = input("Enter Login Page URL: ").strip()
        if not username:
            username = input("Enter Username / Email: ").strip()
        if not password:
            password = getpass.getpass("Enter Password: ")

        all_download_items = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            print(f"[*] Navigating to login portal: {login_url}")
            try:
                await page.goto(login_url, wait_until="networkidle", timeout=30000)
                
                # Fill login credentials using common input selectors
                print("[*] Submitting login credentials...")
                await page.fill("input[type='email'], input[name*='user'], input[name*='login'], input[id*='user']", username)
                await page.fill("input[type='password'], input[name*='pass'], input[id*='pass']", password)
                
                # Submit form
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Log In'), button:has-text('Sign In'), button:has-text('Login')")
                await page.wait_for_load_state("networkidle", timeout=15000)
                print("[*] Login sequence completed successfully.")

                # Navigate to target start URL within the authenticated browser context
                print(f"[*] Navigating to target start URL: {sanitized_start}")
                await page.goto(sanitized_start, wait_until="networkidle", timeout=30000)

                urls_to_visit = [sanitized_start]

                while urls_to_visit:
                    current_url = urls_to_visit.pop(0)
                    clean_current = self._sanitize_url(current_url)
                    if clean_current in self.visited_urls or ScrapingRules.is_high_risk_url(clean_current):
                        continue
                    self.visited_urls.add(clean_current)

                    try:
                        if clean_current != sanitized_start:
                            await page.goto(clean_current, wait_until="networkidle", timeout=20000)
                        
                        content = await page.content()
                        
                        # Inspect keyword filter if active
                        has_keyword = self._matches_keyword(content)

                        rel_path = self._get_relative_path(sanitized_start, clean_current)
                        
                        # Extract links and assets using HTMLDocumentParser
                        nav_links, asset_urls = HTMLDocumentParser.extract_links_and_assets(
                            content, clean_current, allowed_netloc, allowed_base_path
                        )

                        child_links_found = len(nav_links)

                        # Process navigation links
                        for clean_target in nav_links:
                            if clean_target not in self.visited_urls and clean_target not in urls_to_visit:
                                urls_to_visit.append(clean_target)
                                self.log_discovery(clean_target, item_type="page")

                        # Process asset links
                        for clean_asset in asset_urls:
                            if clean_asset not in self.visited_assets:
                                self.visited_assets.add(clean_asset)
                                asset_rel = self._get_relative_path(sanitized_start, clean_asset)
                                all_download_items.append((clean_asset, asset_rel))
                                self.log_discovery(clean_asset, item_type="asset")

                        if not self.keyword_filter or has_keyword or child_links_found > 0:
                            if (clean_current, rel_path) not in all_download_items:
                                if not (self.keyword_filter and child_links_found == 0 and not has_keyword):
                                    all_download_items.append((clean_current, rel_path))

                    except Exception as e:
                        print(f"    [!] Error crawling authenticated page {current_url}: {e}")

            except Exception as e:
                print(f"    [!] Authentication failure or timeout: {e}")
            finally:
                await browser.close()

        print(f"\n[*] Authenticated discovery complete! Total items queued: {len(all_download_items)}")

        # Batch download harvested resources
        batch_size = 200
        for i in range(0, len(all_download_items), batch_size):
            batch = all_download_items[i:i + batch_size]
            print(f"[*] Downloading authenticated batch {i // batch_size + 1} ({len(batch)} files)...")
            await self.downloader.download_batch(batch)

        print("[*] Authenticated crawl and download complete!")

    def crawl(self, start_url: str, login_url: str = None, username: str = None, password: str = None):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url, login_url, username, password))
