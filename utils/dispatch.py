import asyncio
from yarl import URL
from bs4 import BeautifulSoup
from scraper.downloader import UniversalDownloader
from utils import URLUtils
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
    Orchestration utility that probes a target URL, analyzes architectural candidates 
    with confidence scores, presents an interactive selection menu, and dynamically 
    dispatches a coordinated multi-crawler swarm with shared deduplication, leveraging 
    centralized URL sanitization.
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.global_seen_urls = set()

    def _sanitize_url(self, raw_url: str) -> str:
        """Delegates URL sanitization to the centralized URLUtils utility."""
        return URLUtils.sanitize_url(raw_url)

    async def probe_and_route(
        self, 
        start_url: str, 
        forced_profile: str = None, 
        keyword_filter: str = None, 
        non_interactive: bool = False
    ):
        """
        Performs a lightweight Tier 1 probe, evaluates candidate profiles with reasoning,
        prompts the user for swarm execution strategy, or respects overrides/non-interactive flags.
        """
        sanitized_start = self._sanitize_url(start_url)
        print(f"[*] Dispatcher probing target: {sanitized_start}")

        if forced_profile:
            print(f"[*] User override active. Forcing profile: '{forced_profile}'")
            profiles = [forced_profile]
        else:
            # Step 1: Perform lightweight probe of Tier 1 links and capture raw HTML & headers
            sample_urls, raw_html, response_headers = await self._fetch_tier_one_samples(sanitized_start)
            
            # Step 2: Analyze candidates with confidence scores and reasoning
            from config import ScrapingRules
            candidates = ScrapingRules.analyze_profiles_detailed(sample_urls, raw_html, response_headers)
            
            # Step 3: Resolve profiles based on interactivity and user selection
            profiles = self._resolve_profile_selection(candidates, non_interactive=non_interactive)

        # Step 4: Execute multi-crawler dispatch swarm pipeline with shared deduplication
        await self._dispatch_to_crawlers(profiles, sanitized_start, keyword_filter=keyword_filter)

    async def _fetch_tier_one_samples(self, start_url: str) -> tuple[list[str], str, dict]:
        """Fetches the start URL, extracts sample child links, raw HTML, and response headers for probing."""
        sample_urls = []
        raw_html = ""
        response_headers = {}
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
                        clean_target = self._sanitize_url(str(absolute_url))
                        
                        if URL(clean_target).host == allowed_netloc:
                            if clean_target not in sample_urls and clean_target not in self.global_seen_urls:
                                sample_urls.append(clean_target)
                                self.global_seen_urls.add(clean_target)
        except Exception as e:
            print(f"    [!] Warning during probe phase: {e}")
            
        return sample_urls, raw_html, response_headers

    def _resolve_profile_selection(self, candidates: list[dict], non_interactive: bool = False) -> list[str]:
        """Presents ranked architectural candidates and handles user selection modes."""
        print("\n========================================")
        print("     ARCHITECTURAL CANDIDATE ANALYSIS     ")
        print("========================================")
        for idx, cand in enumerate(candidates, 1):
            print(f" [{idx}] {cand['profile'].upper()} (Confidence: {cand['confidence'] * 100:.0f}%)\n     Reason: {cand['reason']}")
        print("-" * 40)

        top_candidate = candidates[0]["profile"]
        all_candidates = [c["profile"] for c in candidates]

        if non_interactive:
            print(f"[*] Non-interactive mode active. Automatically selecting top-ranked profile: '{top_candidate}'")
            return [top_candidate]

        print("Selection Options:")
        print("  [0] or Enter: Run top recommended candidate")
        print("  [a]         : Run ALL applicable candidates as a parallel swarm")
        print("  [n]         : Pick a specific manual profile")
        
        try:
            choice = input("Select an option (0/a/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Input interrupted. Defaulting to top recommended candidate.")
            return [top_candidate]

        if choice == "" or choice == "0":
            print(f"[*] Running recommended candidate: '{top_candidate}'")
            return [top_candidate]
        elif choice == "a":
            print(f"[*] Running all applicable candidates as a swarm: {all_candidates}")
            return all_candidates
        elif choice == "n":
            available_profiles = [
                "universal", "hierarchical", "flat_paged", "asset_index", 
                "sitemap", "feed", "headless", "infinite_scroll", 
                "authenticated", "openapi"
            ]
            print("\nAvailable Profiles:")
            for idx, p in enumerate(available_profiles, 1):
                print(f"  [{idx}] {p}")
            try:
                p_choice = input("Select profile number: ").strip()
                idx_val = int(p_choice) - 1
                if 0 <= idx_val < len(available_profiles):
                    chosen = available_profiles[idx_val]
                    print(f"[*] Manual profile selected: '{chosen}'")
                    return [chosen]
            except Exception:
                pass
            print(f"    [!] Invalid selection. Defaulting to top candidate: '{top_candidate}'")
            return [top_candidate]
        else:
            print(f"[*] Unrecognized option. Defaulting to top candidate: '{top_candidate}'")
            return [top_candidate]

    async def _dispatch_to_crawlers(self, profiles: list[str], start_url: str, keyword_filter: str = None):
        """Delegates execution to multiple specialized crawlers concurrently with shared URL deduplication tracking."""
        print(f"\n[*] Dispatching active crawler swarm: {profiles}")
        
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

        # Run all selected crawlers concurrently as a coordinated swarm
        await asyncio.gather(*tasks)
        print("[*] All dispatched crawler pipelines completed execution.")

    def run(
        self, 
        start_url: str, 
        forced_profile: str = None, 
        keyword_filter: str = None, 
        non_interactive: bool = False
    ):
        """Synchronous wrapper for dispatch execution."""
        asyncio.run(self.probe_and_route(
            start_url, 
            forced_profile=forced_profile, 
            keyword_filter=keyword_filter, 
            non_interactive=non_interactive
        ))
