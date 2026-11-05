import hashlib
import tempfile
from pathlib import Path
from typing import Optional, List
from yarl import URL

class BaseCrawler:
    """
    Shared base utility providing centralized logging, active engine 
    announcements, live-streaming discovery feedback, temporary file management,
    interactive branch selection, and content-based keyword filtering.
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

    def _prompt_branch_selection(self, discovered_branches: List[str]) -> List[str]:
        """
        Presents an interactive branch selection menu after Tier 1 discovery
        to let the user scope down the crawl to a specific year or subdirectory branch.
        """
        if not discovered_branches:
            return []
        
        print(f"\n========================================")
        print(f" [?] BRANCH DISCOVERY CHECKPOINT ({len(discovered_branches)} paths found)")
        print(f"========================================")
        print("  [0] Proceed with ALL discovered branches")
        for idx, branch in enumerate(discovered_branches[:15], 1):
            print(f"  [{idx}] {branch}")
        if len(discovered_branches) > 15:
            print(f"    ... and {len(discovered_branches) - 15} more branches.")
        
        choice = input("\nSelect a specific branch number, or press Enter for all: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(discovered_branches):
                selected = discovered_branches[idx - 1]
                print(f"[*] Scoping crawl strictly to branch: {selected}")
                return [selected]
        
        print("[*] Proceeding with full discovery traversal.")
        return discovered_branches
