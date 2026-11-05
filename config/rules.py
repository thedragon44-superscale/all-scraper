from yarl import URL

class ScrapingRules:
    """
    Centralized utility containing heuristic rules, risk filters, 
    and architectural fingerprinting patterns for target websites.
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
    def fingerprint_architecture(sample_urls: list[str]) -> str:
        """
        Analyzes a batch of discovered sample URLs from Tier 1 to 
        fingerprint the site's architectural profile across the full crawler suite:
        - 'openapi': Developer portals / API specification endpoints
        - 'sitemap': XML index sitemaps
        - 'feed': RSS / Atom chronological feeds
        - 'asset_index': Binary file mirrors and downloadable repositories
        - 'flat_paged': Relies heavily on pagination or query lists
        - 'hierarchical': Deep folder trees and subcategories
        - 'universal': Standard general-purpose fallback crawl
        """
        if not sample_urls:
            return "universal"

        # Check for OpenAPI / Swagger specs
        if any(any(kw in u.lower() for kw in ["swagger", "openapi", "api-docs"]) for u in sample_urls):
            return "openapi"

        # Check for Sitemaps
        if any(u.endswith("sitemap.xml") or "sitemap" in u.lower() for u in sample_urls):
            return "sitemap"

        # Check for Feeds (RSS/Atom)
        if any(any(kw in u.lower() for kw in ["/feed/", "rss.xml", "atom.xml", ".rss", ".atom"]) for u in sample_urls):
            return "feed"

        # Check for Asset / File Repositories
        asset_extensions = {".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".png", ".jpg", ".jpeg"}
        asset_matches = sum(1 for u in sample_urls if URL(u).suffix.lower() in asset_extensions or "download" in u.lower())
        if asset_matches / len(sample_urls) > 0.3:
            return "asset_index"

        # Check for Pagination
        pagination_count = sum(1 for u in sample_urls if ScrapingRules.is_pagination_url(u))
        if pagination_count / len(sample_urls) > 0.3:
            return "flat_paged"

        # Check path depth complexity for hierarchy
        depths = [len(URL(u).path.strip("/").split("/")) for u in sample_urls if URL(u).path]
        avg_depth = sum(depths) / len(depths) if depths else 0

        if avg_depth > 2:
            return "hierarchical"
        
        return "universal" # Default fallback for simple or unstructured sites
