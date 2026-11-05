import asyncio
from .base import BaseCrawler
from pathlib import Path
from yarl import URL
from tqdm import tqdm
from config import DATA_DIR, ScrapingRules
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader

class AssetCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler focused strictly on harvesting binary assets, 
        document repositories, and direct file archives into data/assets/ 
        using multi-core multiprocessing parsing.
        """
        super().__init__(name="AssetCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.asset_output_dir = DATA_DIR / "assets"
        self.asset_output_dir.mkdir(parents=True, exist_ok=True)
        self.visited_urls = set()
        self.visited_assets = set()

    def _get_asset_path(self, start_url: str, current_url: str) -> Path:
        """
        Converts an absolute URL into a safe target path inside the 
        data/assets/ folder directory structure.
        """
        clean_current = self._sanitize_url(current_url)
        start = URL(start_url)
        current = URL(clean_current)
        
        try:
            rel_parts = Path(current.path.strip("/")).relative_to(Path(start.path.strip("/")))
        except ValueError:
            rel_parts = Path(current.path.strip("/"))
            
        rel_str = str(rel_parts).strip("/")
        if not rel_str or rel_str == ".":
            rel_str = "index.html"
            
        return self.asset_output_dir / rel_str

    def _chunk_list(self, lst, n):
        """Yields successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] AssetCrawler active for: {sanitized_start}")
        print(f"[*] Target Asset Destination: {self.asset_output_dir}")
        
        index_pages = [sanitized_start]
        all_download_items = []
        
        # Step 1: Probe the index/repository root page to harvest asset links
        print(f"[*] Scanning repository index for direct assets and files...")
        initial_results = await self.downloader.download_batch([(sanitized_start, self._get_asset_path(sanitized_start, sanitized_start))])
        
        discovered_links = {sanitized_start}
        parse_payloads = []
        file_meta_map = {}

        for url, saved_file in initial_results:
            if not saved_file or not saved_file.exists() or saved_file.suffix.lower() != ".html":
                continue
            try:
                content = saved_file.read_text(encoding="utf-8", errors="ignore")
                file_meta_map[url] = saved_file
                parse_payloads.append((url, content, sanitized_start, allowed_netloc, allowed_base_path))
            except Exception as e:
                print(f"    [!] Error reading repository root index: {e}")

        if parse_payloads:
            print(f"    [⚙] Offloading root index to multi-core process pool...")
            parallel_results = await HTMLDocumentParser.parse_batch_parallel(
                parse_payloads, 
                keyword_filter=self.keyword_filter, 
                max_workers=3
            )

            binary_extensions = {".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".doc", ".docx", ".xls", ".xlsx"}

            for url, has_keyword, nav_links, asset_urls in parallel_results:
                # Process binary assets found on root page
                for clean_target in asset_urls:
                    if ScrapingRules.is_high_risk_url(clean_target):
                        continue
                    if clean_target not in self.visited_assets:
                        self.visited_assets.add(clean_target)
                        target_path = self._get_asset_path(sanitized_start, clean_target)
                        all_download_items.append((clean_target, target_path))
                        self.log_discovery(clean_target, item_type="asset")

                # Process sub-index navigation pages for further discovery
                for clean_target in nav_links:
                    if ScrapingRules.is_high_risk_url(clean_target):
                        continue
                    if clean_target not in discovered_links:
                        discovered_links.add(clean_target)
                        index_pages.append(clean_target)

        # Step 2: Crawl any secondary sub-indices to catch deep-nested assets if present
        sub_index_pairs = [(p, self._get_asset_path(sanitized_start, p)) for p in index_pages if p != sanitized_start]
        if sub_index_pairs:
            print(f"[*] Exploring {len(sub_index_pairs)} sub-index directories...")
            sub_results = await self.downloader.download_batch(sub_index_pairs)
            
            sub_payloads = []
            valid_sub_pages = [res for res in sub_results if res and res[1] and res[1].exists()]
            for url, saved_file in valid_sub_pages:
                if saved_file.suffix.lower() != ".html":
                    continue
                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    sub_payloads.append((url, content, sanitized_start, allowed_netloc, allowed_base_path))
                except Exception as e:
                    print(f"    [!] Error reading sub-index {url}: {e}")

            if sub_payloads:
                print(f"    [⚙] Offloading {len(sub_payloads)} sub-indices to multi-core process pool...")
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
                            target_path = self._get_asset_path(sanitized_start, clean_target)
                            all_download_items.append((clean_target, target_path))
                            self.log_discovery(clean_target, item_type="asset")

        print(f"\n[*] Asset discovery complete! Total files queued for download: {len(all_download_items)}")

        # Step 3: Chunked batch downloads directly into data/assets/ with user checkpoints
        batch_size = 200
        chunks = list(self._chunk_list(all_download_items, batch_size))
        
        if not chunks:
            print("[*] No assets matched the criteria for downloading.")
            return

        print(f"\n[*] Splitting download queue into {len(chunks)} batches (~{batch_size} files per batch).")

        for idx, batch in enumerate(chunks, 1):
            print(f"\n========================================")
            print(f" [?] BATCH CHECKPOINT [{idx}/{len(chunks)}] ({len(batch)} files)")
            print(f"========================================")
            
            print("  Preview of items in this batch:")
            for sample_url, sample_path in batch[:5]:
                print(f"    - {sample_path.name}")
            if len(batch) > 5:
                print(f"    ... and {len(batch) - 5} more files.")

            user_input = input(f"\nProceed with batch [{idx}/{len(chunks)}]? (y = yes, n = skip batch, q = quit): ").strip().lower()
            
            if user_input == 'q':
                print("[*] Download aborted by user.")
                return
            elif user_input == 'n':
                print(f"[*] Skipping batch {idx}...")
                continue
            
            print(f"[*] Downloading batch {idx}/{len(chunks)} to {self.asset_output_dir}...")
            await self.downloader.download_batch(batch)

        print(f"\n[*] Asset harvesting complete! All files saved under {self.asset_output_dir}")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
