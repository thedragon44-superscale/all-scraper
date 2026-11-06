from yarl import URL
from bs4 import BeautifulSoup

class ScrapingRules:
    """
    Centralized utility containing heuristic rules, risk filters, 
    and multi-dimensional architectural fingerprinting patterns with confidence scoring and reasoning.
    """

    @staticmethod
    def is_high_risk_url(url_str: str) -> bool:
        try:
            parsed = URL(url_str)
            path = parsed.path
            risk_indicators = [',', '&', '(', ')', '%2C', '%26', '%28', '%29']
            return any(indicator in path for indicator in risk_indicators)
        except Exception:
            return False

    @staticmethod
    def is_pagination_url(url_str: str) -> bool:
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
    def analyze_profiles_detailed(sample_urls: list[str], raw_html: str = "", response_headers: dict = None) -> list[dict]:
        """
        Analyzes sample URLs, raw HTML structure, and response headers to evaluate 
        candidate profiles with confidence scores and descriptive reasoning.
        """
        response_headers = response_headers or {}
        html_lower = raw_html.lower()
        soup = BeautifulSoup(raw_html, "lxml") if raw_html else None
        
        candidates = []

        # 1. Check for Security Challenges (Cloudflare, Captcha, etc.)
        challenge_markers = ["cf-browser-verification", "challenge-platform", "recaptcha", "turnstile", "ddos-guard"]
        if any(marker in html_lower for marker in challenge_markers):
            candidates.append({
                "profile": "headless",
                "confidence": 0.95,
                "reason": "Security challenge or bot-mitigation wall detected in HTML markup."
            })

        # 2. Check for Authentication / Paywalls
        auth_markers = ["type=\"password\"", "sign-in", "login", "paywall", "subscribe to read"]
        has_auth_form = soup and soup.find("input", {"type": "password"})
        if has_auth_form or any(marker in html_lower for marker in auth_markers):
            candidates.append({
                "profile": "authenticated",
                "confidence": 0.90,
                "reason": "Authentication form or login credential prompt identified."
            })

        # 3. Check for API-First or GraphQL Payloads / OpenAPI Specs
        content_type = response_headers.get("content-type", "").lower()
        if "application/json" in content_type or "application/graphql" in content_type or any("graphql" in u.lower() for u in sample_urls):
            candidates.append({
                "profile": "openapi",
                "confidence": 0.92,
                "reason": "API-first endpoint or JSON/GraphQL payload structure detected."
            })
        elif any(any(kw in u.lower() for kw in ["swagger", "openapi", "api-docs"]) for u in sample_urls):
            candidates.append({
                "profile": "openapi",
                "confidence": 0.98,
                "reason": "Swagger or OpenAPI documentation spec referenced in URLs."
            })

        # 4. Check for Sitemaps
        if any(u.endswith("sitemap.xml") or "sitemap" in u.lower() for u in sample_urls):
            candidates.append({
                "profile": "sitemap",
                "confidence": 0.99,
                "reason": "Sitemap XML index explicitly referenced."
            })

        # 5. Check for Feeds (RSS/Atom)
        if any(any(kw in u.lower() for kw in ["/feed/", "rss.xml", "atom.xml", ".rss", ".atom"]) for u in sample_urls):
            candidates.append({
                "profile": "feed",
                "confidence": 0.95,
                "reason": "Syndication feed format identified in URL structure."
            })

        # 6. Check for Client-Side Rendering / SPAs -> Headless
        spa_indicators = [
            "__next_data__", "window.__nuxt__", "react-root", 
            "app-root", "hydrated", "ng-app", "pdf-viewer", "document-viewer"
        ]
        has_spa_markers = any(marker in html_lower for marker in spa_indicators)
        is_sparse_links = len(sample_urls) <= 3
        
        if has_spa_markers or (is_sparse_links and len(html_lower) > 0):
            candidates.append({
                "profile": "headless",
                "confidence": 0.85 if has_spa_markers else 0.70,
                "reason": "Client-side rendering framework or sparse static link structure detected."
            })

        # 7. Virtualized / Infinite Scroll Swarm Pairing
        scroll_indicators = [
            "virtual", "infinite", "masonry", "scroll-container", 
            "virtualized", "lazy-load", "data-page", "data-index", "observer"
        ]
        has_scroll_markers = any(marker in html_lower for marker in scroll_indicators)
        has_headless = any(c["profile"] == "headless" for c in candidates)
        
        if has_scroll_markers or has_headless:
            candidates.append({
                "profile": "infinite_scroll",
                "confidence": 0.88 if has_scroll_markers else 0.75,
                "reason": "Virtualization layout attributes or dynamic headless container structure present."
            })

        # 8. Check for Asset / File Repositories
        asset_extensions = {".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".png", ".jpg", ".jpeg"}
        asset_matches = sum(1 for u in sample_urls if URL(u).suffix.lower() in asset_extensions or "download" in u.lower())
        if (sample_urls and asset_matches / max(len(sample_urls), 1) > 0.3) or "pdf" in html_lower or "download" in html_lower:
            candidates.append({
                "profile": "asset_index",
                "confidence": 0.85,
                "reason": "High density of downloadable binary assets or file repository references."
            })

        # 9. Check for Pagination
        pagination_count = sum(1 for u in sample_urls if ScrapingRules.is_pagination_url(u))
        if pagination_count / max(len(sample_urls), 1) > 0.3:
            candidates.append({
                "profile": "flat_paged",
                "confidence": 0.90,
                "reason": "Frequent pagination query parameters or path segments detected."
            })

        # 10. Check path depth complexity for hierarchy
        depths = [len(URL(u).path.strip("/").split("/")) for u in sample_urls if URL(u).path]
        avg_depth = sum(depths) / len(depths) if depths else 0
        if avg_depth > 2:
            candidates.append({
                "profile": "hierarchical",
                "confidence": 0.75,
                "reason": "Deep nested directory path tree structure."
            })

        # Fallback if no specific profiles matched
        if not candidates:
            candidates.append({
                "profile": "universal",
                "confidence": 0.60,
                "reason": "No specialized structural signatures matched; defaulting to universal crawler."
            })

        return candidates

    @staticmethod
    def fingerprint_architecture(sample_urls: list[str], raw_html: str = "", response_headers: dict = None) -> list[str]:
        """
        Backward-compatible wrapper that returns a list of unique profile names 
        derived from detailed confidence and reasoning analysis.
        """
        candidates = ScrapingRules.analyze_profiles_detailed(sample_urls, raw_html, response_headers)
        
        # Print out reasoning for transparency and developer telemetry
        print("\n[*] Architectural Candidate Analysis:")
        for cand in candidates:
            print(f"    - [{cand['profile'].upper()}] Confidence: {cand['confidence'] * 100:.0f}% | Reason: {cand['reason']}")
            
        # Deduplicate profile names while preserving detection order
        seen = set()
        profiles = []
        for cand in candidates:
            p = cand["profile"]
            if p not in seen:
                seen.add(p)
                profiles.append(p)

        return profiles
