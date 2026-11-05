from yarl import URL
from bs4 import BeautifulSoup

class ScrapingRules:
    """
    Centralized utility containing heuristic rules, risk filters, 
    and multi-dimensional architectural fingerprinting patterns for target websites.
    """

    @staticmethod
    def is_high_risk_url(url_str: str) -> bool:
        """
        Evaluates whether a URL path contains high-risk punctuation 
        (commas, ampersands, parentheses) known to trigger redirect loops 
        on static mirror archives.
        """
        try:
            parsed = URL(url_str)
            path = parsed.path
            risk_indicators = [',', '&', '(', ')', '%2C', '%26', '%28', '%29']
            return any(indicator in path for indicator in risk_indicators)
        except Exception:
            return False

    @staticmethod
    def is_pagination_url(url_str: str) -> bool:
        """
        Detects if a URL represents a pagination page based on common 
        query parameters or path conventions.
        """
        try:
            parsed = URL(url_str)
            query_keys = parsed.query.keys()
            pagination_params = {'page', 'p', 'offset', 'start', 'cursor'}
            if any(param in query_keys for param in pagination_params):
                return True
            
            path_segments = parsed.path.strip("/").split("/")
            if any(seg in {"page", "p", "pagination"} for seg in path_segments):
                return True
                
            return False
        except Exception:
            return False

    @staticmethod
    def fingerprint_architecture(sample_urls: list[str], raw_html: str = "") -> list[str]:
        """
        Analyzes sample URLs and raw HTML structure to dynamically select 
        and combine multiple specialized crawler profiles without hardcoded domain references.
        """
        profiles = set()
        html_lower = raw_html.lower()
        soup = BeautifulSoup(raw_html, "lxml") if raw_html else None

        # 1. Check for OpenAPI / Swagger specs
        if any(any(kw in u.lower() for kw in ["swagger", "openapi", "api-docs"]) for u in sample_urls):
            profiles.add("openapi")

        # 2. Check for Sitemaps
        if any(u.endswith("sitemap.xml") or "sitemap" in u.lower() for u in sample_urls):
            profiles.add("sitemap")

        # 3. Check for Feeds (RSS/Atom)
        if any(any(kw in u.lower() for kw in ["/feed/", "rss.xml", "atom.xml", ".rss", ".atom"]) for u in sample_urls):
            profiles.add("feed")

        # 4. Check for Client-Side Rendering / SPA Footprints -> Headless
        spa_indicators = [
            "__next_data__", "window.__nuxt__", "react-root", 
            "app-root", "hydrated", "ng-app", "pdf-viewer", "document-viewer"
        ]
        has_spa_markers = any(marker in html_lower for marker in spa_indicators)
        is_sparse_links = len(sample_urls) <= 3
        
        if has_spa_markers or (is_sparse_links and len(html_lower) > 0):
            profiles.add("headless")

        # 5. Check for Virtualization / Infinite Scroll Structural Markers
        scroll_indicators = [
            "virtual", "infinite", "masonry", "scroll-container", 
            "virtualized", "lazy-load", "data-page", "data-index", "observer"
        ]
        has_scroll_markers = any(marker in html_lower for marker in scroll_indicators)
        
        if has_scroll_markers or ("headless" in profiles and soup and len(soup.find_all("script")) > 5):
            profiles.add("infinite_scroll")

        # 6. Check for Asset / File Repositories
        asset_extensions = {".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".png", ".jpg", ".jpeg"}
        asset_matches = sum(1 for u in sample_urls if URL(u).suffix.lower() in asset_extensions or "download" in u.lower())
        if (sample_urls and asset_matches / len(sample_urls) > 0.3) or "pdf" in html_lower or "download" in html_lower:
            profiles.add("asset_index")

        # 7. Check for Pagination
        pagination_count = sum(1 for u in sample_urls if ScrapingRules.is_pagination_url(u))
        if pagination_count / max(len(sample_urls), 1) > 0.3:
            profiles.add("flat_paged")

        # 8. Check path depth complexity for hierarchy
        depths = [len(URL(u).path.strip("/").split("/")) for u in sample_urls if URL(u).path]
        avg_depth = sum(depths) / len(depths) if depths else 0
        if avg_depth > 2:
            profiles.add("hierarchical")

        # Fallback if no specific profiles matched
        if not profiles:
            profiles.add("universal")

        return list(profiles)
