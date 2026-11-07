from pathlib import Path
from typing import Iterable, Optional
from yarl import URL

class URLUtils:
    """
    Utility class for robust URL parsing, domain-matching, and path sanitization.
    """

    @staticmethod
    def sanitize_url(url_str: str) -> str:
        """
        Sanitizes and normalizes a URL string by stripping fragments and ensuring correct formatting.
        """
        try:
            parsed = URL(url_str.strip())
            return str(parsed.with_fragment(""))
        except Exception:
            return url_str.strip()

    @staticmethod
    def url_is_from_any_domain(url_str: str, allowed_domains: Iterable[str]) -> bool:
        """
        Verifies whether a URL belongs to any of the allowed base domains or their subdomains.
        """
        try:
            parsed = URL(url_str)
            host = parsed.host
            if not host:
                return False
            
            host = host.lower()
            for domain in allowed_domains:
                domain = domain.lower().strip()
                if host == domain or host.endswith(f".{domain}"):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_relative_path(start_url: str, current_url: str) -> Path:
        """
        Derives a secure, normalized local target file path from a start URL and current URL.
        """
        try:
            start = URL(start_url)
            current = URL(current_url)
            
            start_path = start.path.rstrip("/")
            current_path = current.path
            
            if current_path.startswith(start_path):
                rel_str = current_path[len(start_path):].strip("/")
            else:
                rel_str = current_path.strip("/")
                
            if not rel_str or rel_str == ".":
                rel_str = "index.html"
            
            path_obj = Path(rel_str)
            if not path_obj.suffix and not rel_str.endswith("/"):
                path_obj = Path(f"{rel_str}.html")
            elif rel_str.endswith("/"):
                path_obj = path_obj / "index.html"
                
            return path_obj
        except Exception:
            return Path("fallback_page.html")
