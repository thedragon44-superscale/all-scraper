import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from yarl import URL
from tqdm import tqdm
from config import ScrapingRules
from parser.html_parser import HTMLDocumentParser
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

class HierarchicalCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler for deep tree structures, documentation archives, 
        and directory trees, featuring automated top-level branch sniffing, 
        parallel multi-core process pool parsing, and content-based keyword filtering.
        """
        super().__init__(name="HierarchicalCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.visited_urls = set()
        self.visited_assets = set()

    def _chunk_list(self, lst, n):
        """Yields successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        start = URL(sanitized_start)
        allowed_netloc = start.host
        allowed_base_path = start.path.rstrip("/")

        print(f"[*] HierarchicalCrawler active for: {sanitized_start}")
        print(f"[*] Scope Locked -> Host: {allowed_netloc} | Base Path: {allowed_base_path}")
        
        current_tier = [sanitized_start]
        all_download_items = []
        tier_count = 0
        selected_branch = None

        # ==========================================
        # PHASE 1: DISCOVERY & AUTO-SNIFFING (MULTI-CORE)
        # ==========================================
        while current_tier:
            tier_count += 1
            batch_pairs = []
            for url_str in current_tier:
                clean_url = self._sanitize_url(url_str)
                
                if clean_url not in self.visited_urls and not ScrapingRules.is_high_risk_url(clean_url):
                    self.visited_urls.add(clean_url)
                    batch_pairs.append((clean_url, self._get_relative_path(sanitized_start, clean_url)))

            if not batch_pairs:
                break

            print(f"\n[+] Discovery Tier {tier_count}: Processing {len(batch_pairs)} endpoints...")
            downloaded_results = await self.downloader.download_batch(batch_pairs)
            next_tier = []

            # AUTO-SNIFFING TOP-LEVEL BRANCH MENU (Triggered right after Tier 1)
            if tier_count == 1 and not selected_branch:
                discovered_branches = []
                for url, saved_file in downloaded_results:
                    if not saved_file or not saved_file.exists() or saved_file.suffix.lower() != ".html":
                        continue
                    temp_path = None
                    try:
                        content = saved_file.read_text(encoding="utf-8", errors="ignore")
                        temp_path = self._create_temp_discovery_file(content)
                        soup = BeautifulSoup(temp_path.read_text(encoding="utf-8", errors="ignore"), "lxml")
                        for a_tag in soup.find_all("a", href=True):
                            href = a_tag["href"].strip()
                            if not href or href.startswith("javascript:") or href.startswith("#"):
                                continue
                            absolute_url = URL(url).join(URL(href))
                            clean_target = self._sanitize_url(str(absolute_url))
                            if ScrapingRules.is_high_risk_url(clean_target):
                                continue
                            parsed_target = URL(clean_target)
                            if parsed_target.host == allowed_netloc and parsed_target.path.startswith(allowed_base_path):
                                if clean_target not in discovered_branches and clean_target != sanitized_start:
                                    discovered_branches.append(clean_target)
                    except Exception:
                        pass
                    finally:
                        self._cleanup_temp_file(temp_path)
                
                if discovered_branches:
                    discovered_branches.sort()
                    selected_branches = self._prompt_branch_selection(discovered_branches)
                    if selected_branches and len(selected_branches) == 1 and selected_branches[0] in discovered_branches:
                        selected_branch = selected_branches[0]
                        path_part = URL(selected_branch).path.strip("/").split("/")[-1]
                        print(f"\n[*] Scope locked to single branch: {path_part} ({selected_branch})")
                        next_tier = [selected_branch]
                    else:
                        print("\n[*] Proceeding with full archive crawl across all branches...")

            # Prepare batch items for parallel process pool offloading
            valid_results = [res for res in downloaded_results if res and res[1] and res[1].exists()]
            parse_payloads = []
            file_meta_map = {}

            for url, saved_file in valid_results:
                rel_path = self._get_relative_path(sanitized_start, url)
                
                if saved_file.suffix.lower() != ".html":
                    if (url, rel_path) not in all_download_items:
                        all_download_items.append((url, rel_path))
                    continue

                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    file_meta_map[url] = rel_path
                    parse_payloads.append((url, content, sanitized_start, allowed_netloc, allowed_base_path))
                except Exception as e:
                    print(f"    [!] Error reading file for {url}: {e}")

            if parse_payloads:
                print(f"    [⚙] Offloading {len(parse_payloads)} HTML files to multi-core process pool...")
                parallel_results = await HTMLDocumentParser.parse_batch_parallel(
                    parse_payloads, 
                    keyword_filter=self.keyword_filter, 
                    max_workers=3
                )

                for url, has_keyword, nav_links, asset_urls in parallel_results:
                    rel_path = file_meta_map.get(url)
                    child_links_found = len(nav_links)

                    # 1. Process discovered navigation links
                    for clean_target in nav_links:
                        if ScrapingRules.is_high_risk_url(clean_target):
                            continue
                        
                        if clean_target not in self.visited_urls and clean_target not in next_tier and clean_target not in current_tier:
                            if selected_branch and not clean_target.startswith(selected_branch):
                                continue
                            next_tier.append(clean_target)

                    # 2. Process discovered binary/asset links
                    for clean_asset in asset_urls:
                        if ScrapingRules.is_high_risk_url(clean_asset):
                            continue
                        
                        if clean_asset not in self.visited_assets:
                            self.visited_assets.add(clean_asset)
                            asset_rel = self._get_relative_path(sanitized_start, clean_asset)
                            all_download_items.append((clean_asset, asset_rel))

                    # 3. Evaluate keyword filter & queue page if valid
                    if not self.keyword_filter or has_keyword or child_links_found > 0:
                        if (url, rel_path) not in all_download_items:
                            if not (self.keyword_filter and child_links_found == 0 and not has_keyword):
                                all_download_items.append((url, rel_path))

            current_tier = next_tier

        print(f"\n[*] Discovery complete! Total items queued: {len(all_download_items)}")

        # ==========================================
        # PHASE 2: CHUNKED BATCH DOWNLOADS
        # ==========================================
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

        print(f"\n[*] Hierarchical crawling and downloading complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
