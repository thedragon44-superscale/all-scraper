import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from yarl import URL
from tqdm import tqdm
from config import DATA_DIR
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader
from utils import URLUtils
from .base import BaseCrawler

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class HeadlessCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        super().__init__(name="HeadlessCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()

    def _sanitize_url(self, raw_url: str) -> str:
        """Delegates URL sanitization to the centralized URLUtils utility."""
        return URLUtils.sanitize_url(raw_url)

    async def crawl_async(self, start_url: str):
        if not PLAYWRIGHT_AVAILABLE:
            print("[!] Playwright is not installed.")
            print("[!] Please run: pip install playwright && playwright install chromium")
            return

        sanitized_start = self._sanitize_url(start_url)
        print(f"[*] HeadlessCrawler active (Sequential Element Capture Engine) for: {sanitized_start}")

        output_dir = DATA_DIR / "Scribd"
        output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 1024},
                device_scale_factor=1.0
            )
            page = await context.new_page()

            print(f"[*] Navigating to target: {sanitized_start}")
            try:
                await page.goto(sanitized_start, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4.0)
            except Exception as e:
                print(f"[!] Navigation error: {e}")
                await browser.close()
                return

            print("[*] Automatically detecting total pages...")
            total_pages = await page.evaluate("""() => {
                const scripts = document.querySelectorAll("script[type='application/ld+json']");
                for (let s of scripts) {
                    try {
                        let data = JSON.parse(s.innerText);
                        if (data.numberOfPages) return parseInt(data.numberOfPages);
                        if (Array.isArray(data)) {
                            for (let item of data) {
                                if (item.numberOfPages) return parseInt(item.numberOfPages);
                            }
                        }
                    } catch(e) {}
                }
                const elements = document.querySelectorAll('[data-page-number], [id^="outer_page_"], [id^="page_"]');
                let max = 0;
                elements.forEach(el => {
                    let num = 0;
                    if (el.dataset && el.dataset.pageNumber) {
                        num = parseInt(el.dataset.pageNumber);
                    } else {
                        let match = el.id.match(/\\d+/);
                        if (match) num = parseInt(match[0]);
                    }
                    if (num > max) max = num;
                });
                return max > 0 ? max : 80;
            }""")
            
            print(f"[+] Target document page count identified: {total_pages}")
            print(f"[*] Beginning sequential element screenshot captures into: {output_dir}")

            successful = 0
            for page_num in range(1, total_pages + 1):
                file_path = output_dir / f"page_{page_num:03d}.png"
                if file_path.exists() and file_path.stat().st_size > 5000:
                    print(f"[=] Page {page_num:03d}: Already cached. Skipping.")
                    successful += 1
                    continue

                selector = f"#outer_page_{page_num}, #page_{page_num}, [data-page-number='{page_num}']"
                attempts = 0
                captured = False

                while attempts < 5 and not captured:
                    attempts += 1
                    try:
                        element = await page.query_selector(selector)
                        if not element:
                            await page.evaluate("window.scrollBy(0, 400);")
                            await asyncio.sleep(1.0)
                            continue

                        await element.scroll_into_view_if_needed(timeout=10000)
                        await asyncio.sleep(0.5)
                        
                        await element.screenshot(path=str(file_path))
                        if file_path.exists() and file_path.stat().st_size > 5000:
                            captured = True
                            successful += 1
                            print(f"[+] Page {page_num:03d}: Captured successfully.")
                        else:
                            await asyncio.sleep(1.0)
                    except Exception:
                        await page.evaluate("window.scrollBy(0, 200);")
                        await asyncio.sleep(0.8)

                if not captured:
                    print(f"[!] Page {page_num:03d}: Failed to capture after attempts.")

            await browser.close()
        print(f"\n[*] Headless crawl complete! Successfully captured {successful} pages into {output_dir}")

    def crawl(self, start_url: str):
        asyncio.run(self.crawl_async(start_url))
