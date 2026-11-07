import asyncio
from pathlib import Path
from yarl import URL
from tqdm import tqdm
from config import ScrapingRules
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

class FlatCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler for flat sites, listing archives, and 
        pagination-heavy directories using multi-core parsing and keyword filtering.
        """
        super().__init__(name="FlatCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()
        self.visited_assets = set()
        
        # Initialize default request headers using case-insensitive mapping
        self.default_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"

    def _chunk_list(self, lst, n):
        """Yields successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] FlatCrawler active for: {sanitized_start}")
        print(f"[*] Scope Locked -> Host: {allowed_netloc} (Pagination & List Optimized)")
        
        pages_to_crawl = [sanitized_start]
        all_download_items = []
        
        # Step 1: Probe start page to discover pagination links and listing nodes
        print(f"[*] Probing start page for pagination patterns...")
        initial_results = await self.downloader.download_batch([(sanitized_start, self._get_relative_path(sanitized_start, sanitized_start))])
        
        discovered_pages = {sanitized_start}
        parse_payloads = []

        for url, saved_file in initial_results:
            if not saved_file or not saved_file.exists() or saved_file.suffix.lower() != ".html":
                continue
            
            all_download_items.append((url, self._get_relative_path(sanitized_start, url)))
            try:
                content = saved_file.read_text(encoding="utf-8", errors="ignore")
                parse_payloads.append((url, content, sanitized_start, allowed_netloc, allowed_base_path))
            except Exception as e:
                print(f"    [!] Error reading initial page: {e}")

        if parse_payloads:
            print(f"    [⚙] Offloading root page to multi-core process pool...")
            parallel_results = await HTMLDocumentParser.parse_batch_parallel(
                parse_payloads, 
                keyword_filter=self.keyword_filter, 
                max_workers=3
            )

            for url, has_keyword, nav_links, asset_urls in parallel_results:
                for clean_target in nav_links:
                    if ScrapingRules.is_high_risk_url(clean_target):
                        continue
                    if ScrapingRules.is_pagination_url(clean_target):
                        if clean_target not in discovered_pages:
                            discovered_pages.add(clean_target)
                            pages_to_crawl.append(clean_target)
                            self.log_discovery(clean_target, item_type="page")

        print(f"[*] Discovered {len(pages_to_crawl)} pagination/list pages.")

        # Step 2: Download all discovered listing/pagination pages with multi-core parsing
        page_batch_pairs = [(p, self._get_relative_path(sanitized_start, p)) for p in pages_to_crawl if p != sanitized_start]
        if page_batch_pairs:
            print(f"[*] Fetching pagination pages...")
            paged_results = await self.downloader.download_batch(page_batch_pairs)
            
            sub_payloads = []
            valid_pages = [res for res in paged_results if res and res[1] and res[1].exists()]
            for url, saved_file in valid_pages:
                rel_path = self._get_relative_path(sanitized_start, url)
                if (url, rel_path) not in all_download_items:
                    all_download_items.append((url, rel_path))

                if saved_file.suffix.lower() != ".html":
                    continue

                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    sub_payloads.append((url, content, sanitized_start, allowed_netloc, allowed_base_path))
                except Exception as e:
                    print(f"    [!] Error reading pagination page {url}: {e}")

            if sub_payloads:
                print(f"    [⚙] Offloading {len(sub_payloads)} pagination pages to multi-core process pool...")
                sub_parallel_results = await HTMLDocumentParser.parse_batch_parallel(
                    sub_payloads, 
                    keyword_filter=self.keyword_filter, 
                    max_workers=3
                )

                for url, has_keyword, nav_links, asset_urls in sub_parallel_results:
                    for clean_target in asset_urls:
                        if ScrapingRules.is_high_risk_url(clean_target):
                            continue
                        if clean_target not in self.visited_assets:
                            self.visited_assets.add(clean_target)
                            target_rel = self._get_relative_path(sanitized_start, clean_target)
                            all_download_items.append((clean_target, target_rel))
                            self.log_discovery(clean_target, item_type="asset")

        print(f"\n[*] Flat discovery complete! Total items queued: {len(all_download_items)}")

        # Step 3: Chunked batch downloads with user checkpoints
        batch_size = 200
        chunks = list(self._chunk_list(all_download_items, batch_size))
        
        if not chunks:
            print("[*] No items matched the criteria for downloading.")
            return

        print(f"\n[*] Splitting download queue into {len(chunks)} batches (~{batch_size} files per batch).")

        for idx, batch in enumerate(chunks, 1):
            print(f"\n========================================")
            print(f" [?] BATCH CHECKPOINT [{idx}/{len(chunks)}] ({len(batch)} files)")
            print(f"========================================")
            
            print("  Preview of items in this batch:")
            for sample_url, sample_path in batch[:5]:
                print(f"    - {sample_path}")
            if len(batch) > 5:
                print(f"    ... and {len(batch) - 5} more files.")

            user_input = input(f"\nProceed with batch [{idx}/{len(chunks)}]? (y = yes, n = skip batch, q = quit): ").strip().lower()
            
            if user_input == 'q':
                print("[*] Download aborted by user.")
                return
            elif user_input == 'n':
                print(f"[*] Skipping batch {idx}...")
                continue
            
            print(f"[*] Downloading batch {idx}/{len(chunks)}...")
            await self.downloader.download_batch(batch)

        print(f"\n[*] Flat crawling and downloading complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
