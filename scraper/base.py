import hashlib
import tempfile
import sys
import collections
from pathlib import Path
from typing import Optional, List, Any, Self, TypeVar
from yarl import URL
from utils import URLUtils

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")

class CaseInsensitiveDict(collections.UserDict[str | bytes, Any]):
    """
    A dict-like structure that accepts strings or bytes as keys and allows 
    case-insensitive lookups, preventing header collision and lookup failures.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._keys: dict[str | bytes, Any] = {}
        super().__init__(*args, **kwargs)

    def __getitem__(self, key: str | bytes) -> Any:
        normalized_key = self._normkey(key)
        return super().__getitem__(self._keys[normalized_key.lower()])

    def __setitem__(self, key: str | bytes, value: Any) -> None:
        normalized_key = self._normkey(key)
        try:
            lower_key = self._keys[normalized_key.lower()]
            del self[lower_key]
        except KeyError:
            pass
        super().__setitem__(normalized_key, self._normvalue(value))
        self._keys[normalized_key.lower()] = normalized_key

    def __delitem__(self, key: str | bytes) -> None:
        normalized_key = self._normkey(key)
        stored_key = self._keys.pop(normalized_key.lower())
        super().__delitem__(stored_key)

    def __contains__(self, key: str | bytes) -> bool:
        normalized_key = self._normkey(key)
        return normalized_key.lower() in self._keys

    def __copy__(self) -> Self:
        new = self.__class__()
        new.data = self.data.copy()
        new._keys = self._keys.copy()
        return new

    copy = __copy__

    def __ior__(self, other: Any) -> Self:
        self.update(other)
        return self

    def _normkey(self, key: str | bytes) -> str | bytes:
        if isinstance(key, bytes):
            return key.decode("utf-8", errors="replace")
        return key

    def _normvalue(self, value: Any) -> Any:
        return value


class BaseCrawler:
    """
    Shared base utility providing centralized logging, active engine 
    announcements, live-streaming event telemetry, temporary file management,
    universal per-tier branch scoping, content-based keyword filtering, and 
    safe asset URL handling.
    """
    def __init__(self, name: str, max_concurrent: int = 3, keyword_filter: Optional[str] = None):
        self.crawler_name = name
        self.max_concurrent = max_concurrent
        self.keyword_filter = keyword_filter
        self.default_headers = CaseInsensitiveDict()
        self._announce_engine()

    def _announce_engine(self):
        print(f"\n========================================")
        print(f" [+] ACTIVE CRAWLER ENGINE: {self.crawler_name}")
        print(f"========================================")
        if self.keyword_filter:
            print(f" [*] Keyword Filter Active: \"{self.keyword_filter}\"")

    def log_event(self, message: str):
        """Standardized event logging helper with crawler tag and forced flush for live terminal telemetry."""
        print(f"[*] [{self.crawler_name}] {message}", flush=True)

    def log_discovery(self, target_url: str, item_type: str = "page"):
        """Streams live discovery logs in real-time with the crawler's name tag."""
        if item_type == "asset":
            print(f"    [+] [{self.crawler_name}] Discovered asset file: {target_url}", flush=True)
        else:
            print(f"    [+] [{self.crawler_name}] Discovered page link: {target_url}", flush=True)

    def log_tier_status(self, tier_num: int, message: str):
        """Standardized tier transition and status reporting for all crawlers."""
        self.log_event(f"Tier {tier_num} Status: {message}")

    def _transform_asset_url(self, raw_url: str) -> str:
        """Preserves signed CDN tokens without modification to prevent expiration failures."""
        return raw_url

    def _sanitize_url(self, raw_url: str) -> str:
        """Delegates URL sanitization to the centralized URLUtils utility."""
        return URLUtils.sanitize_url(raw_url)

    def _get_relative_path(self, start_url: str, current_url: str) -> str:
        """Builds local relative path structures safely."""
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
        content_hash = hashlib.md5(content.encode('utf-8', errors='ignore')).hexdigest()
        temp_path = Path(tempfile.gettempdir()) / f".tmp_{content_hash}.html"
        temp_path.write_text(content, encoding='utf-8', errors='ignore')
        return temp_path

    def _cleanup_temp_file(self, temp_path: Path):
        try:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

    def _matches_keyword(self, text_content: str) -> bool:
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
        if not tier_urls:
            return []

        clean_urls = sorted(list(set(tier_urls)))
        branches_map = {}
        for u in clean_urls:
            try:
                parsed = URL(u)
                segments = [s for s in parsed.path.strip("/").split("/") if s]
                branch_key = f"/{segments[0]}/" if segments else "/"
                if branch_key not in branches_map:
                    branches_map[branch_key] = []
                branches_map[branch_key].append(u)
            except Exception:
                if "/" not in branches_map:
                    branches_map["/"] = []
                branches_map["/"].append(u)

        branch_keys = sorted(list(branches_map.keys()))

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
        return self.select_branches(discovered_branches, tier_num=1, branch_prompt_mode="all", non_interactive=False)
