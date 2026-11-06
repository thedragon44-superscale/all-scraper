import hashlib
import tempfile
import sys
from pathlib import Path
from typing import Optional, List
from yarl import URL

class BaseCrawler:
    """
    Shared base utility providing centralized logging, active engine 
    announcements, live-streaming discovery feedback, temporary file management,
    universal per-tier branch scoping with path grouping, pagination, and deduplication, 
    and content-based keyword filtering.
    """
    def __init__(self, name: str, max_concurrent: int = 3, keyword_filter: Optional[str] = None):
        self.crawler_name = name
        self.max_concurrent = max_concurrent
        self.keyword_filter = keyword_filter
        self._announce_engine()

    def _announce_engine(self):
        print(f"\n========================================")
        print(f" [+] ACTIVE CRAWLER ENGINE: {self.crawler_name}")
        print(f"========================================")
        if self.keyword_filter:
            print(f" [*] Keyword Filter Active: \"{self.keyword_filter}\"")

    def log_discovery(self, target_url: str, item_type: str = "page"):
        """Streams live discovery logs in real-time with the crawler's name tag."""
        if item_type == "asset":
            print(f"    [+] [{self.crawler_name}] Discovered asset file: {target_url}")
        else:
            print(f"    [+] [{self.crawler_name}] Discovered page link: {target_url}")

    def _sanitize_url(self, raw_url: str) -> str:
        """Shared URL sanitization helper."""
        try:
            base_url = raw_url.split("#")[0]
            url_obj = URL(base_url)
            decoded_path = url_obj.path.replace("%2F", "/")
            if not Path(decoded_path).suffix and not decoded_path.endswith("/"):
                decoded_path += "/"
            reconstructed = url_obj.with_path(decoded_path).with_query(url_obj.query)
            return str(reconstructed)
        except Exception:
            return raw_url.split("#")[0]

    def _get_relative_path(self, start_url: str, current_url: str) -> str:
        """Shared relative path builder."""
        clean_current = self._sanitize_url(current_url)
        start = URL(start_url)
        current = URL(clean_current)
        
        try:
            rel_parts = Path(current.path.strip("/")).relative_to(Path(start.path.strip("/")))
        except ValueError:
            rel_parts = Path(current.path.strip("/"))
            
        rel_str = str(rel_parts).strip("/")
        if not rel_str or rel_str == ".":
            return "index.html"
        
        valid_extensions = {".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".zip"}
        if Path(rel_str).suffix.lower() in valid_extensions:
            return rel_str
            
        return f"{rel_str}.html"

    def _create_temp_discovery_file(self, content: str) -> Path:
        """
        Creates a thread-safe, hash-based temporary file for in-memory DOM parsing
        that is automatically unlinked after analysis to prevent disk bloat.
        """
        content_hash = hashlib.md5(content.encode('utf-8', errors='ignore')).hexdigest()
        temp_path = Path(tempfile.gettempdir()) / f".tmp_{content_hash}.html"
        temp_path.write_text(content, encoding='utf-8', errors='ignore')
        return temp_path

    def _cleanup_temp_file(self, temp_path: Path):
        """Safely unlinks and removes temporary discovery files from disk."""
        try:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

    def _matches_keyword(self, text_content: str) -> bool:
        """
        Inspects parsed text content against the optional keyword filter.
        Returns True if no filter is set or if the keyword is found.
        """
        if not self.keyword_filter:
            return True
        return self.keyword_filter.lower() in text_content.lower()

    def select_branches(
        self, 
        tier_urls: List[str], 
        tier_num: int = 1, 
        branch_prompt_mode: str = "first", 
        non_interactive: bool = False
    ) -> List[str]:
        """
        Universal per-tier branch scoping method inherited by all crawlers.
        Handles path grouping, prefix deduplication, pagination, interactive menus, 
        and non-TTY/non-interactive safety fallbacks.
        """
        if not tier_urls:
            return []

        # Deduplicate and normalize URLs
        clean_urls = sorted(list(set(tier_urls)))

        # Group URLs by distinct first-level path segments
        branches_map = {}
        for u in clean_urls:
            try:
                parsed = URL(u)
                segments = [s for s in parsed.path.strip("/").split("/") if s]
                if segments:
                    branch_key = f"/{segments[0]}/"
                else:
                    branch_key = "/"
                if branch_key not in branches_map:
                    branches_map[branch_key] = []
                branches_map[branch_key].append(u)
            except Exception:
                if "/" not in branches_map:
                    branches_map["/"] = []
                branches_map["/"].append(u)

        branch_keys = sorted(list(branches_map.keys()))

        # Guard checks for non-interactive execution, non-TTY streams, or prompt mode constraints
        if len(branch_keys) <= 1 or branch_prompt_mode == "none" or non_interactive or not sys.stdin.isatty():
            return clean_urls

        if branch_prompt_mode == "first" and tier_num > 1:
            return clean_urls

        print(f"\n========================================")
        print(f" [?] TIER {tier_num} BRANCH DISCOVERY CHECKPOINT ({len(branch_keys)} branch groups found)")
        print(f"========================================")
        print("  [0] Proceed with ALL branch groups")
        print("  [s] Skip remaining tier prompts for this crawl")
        print("  [q] Graceful abort (finish pending downloads and exit)")
        
        # Paginated display limit
        display_limit = 15
        for idx, b_key in enumerate(branch_keys[:display_limit], 1):
            sample_count = len(branches_map[b_key])
            print(f"  [{idx}] {b_key} ({sample_count} links)")
        if len(branch_keys) > display_limit:
            print(f"    ... and {len(branch_keys) - display_limit} more branch groups.")

        try:
            choice = input("\nSelect branch number(s) [e.g. 1, 2 or 0/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Input interrupted. Defaulting to all discovered branches.")
            return clean_urls

        if choice == "q":
            print("\n[*] Graceful abort requested by user. Exiting pipeline.")
            sys.exit(0)
        elif choice == "s":
            print("\n[*] Skipping remaining tier branch prompts.")
            return clean_urls
        elif choice == "" or choice == "0":
            return clean_urls

        # Parse user selections (supports comma or space separation)
        selected_urls = []
        indices = []
        for part in choice.replace(",", " ").split():
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(branch_keys):
                    indices.append(idx - 1)

        if indices:
            for idx in indices:
                b_key = branch_keys[idx]
                selected_urls.extend(branches_map[b_key])
            print(f"[*] Scoping crawl strictly to {len(indices)} selected branch group(s).")
            return selected_urls

        print("[*] Unrecognized selection. Defaulting to all discovered branches.")
        return clean_urls

    def _prompt_branch_selection(self, discovered_branches: List[str]) -> List[str]:
        """Backward-compatible wrapper mapping to select_branches at Tier 1."""
        return self.select_branches(discovered_branches, tier_num=1, branch_prompt_mode="all", non_interactive=False)
