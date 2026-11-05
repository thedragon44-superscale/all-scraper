import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Tuple, Optional, Set
from bs4 import BeautifulSoup
from yarl import URL

# Standard whitelists for path validation
VALID_EXTENSIONS: Set[str] = {
    ".html", ".htm", ".pdf", ".png", ".jpg", 
    ".jpeg", ".svg", ".gif", ".webp", ".zip"
}

BINARY_EXTENSIONS: Set[str] = {
    ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".zip"
}

HIGH_RISK_PATTERNS: Set[str] = {
    "login", "logout", "signin", "signout", "auth", 
    "register", "cart", "checkout", "account"
}


def parse_document_worker(payload: Tuple[str, str, str, str, str, Optional[str]]) -> Tuple[str, bool, List[str], List[str]]:
    """
    Top-level, picklable worker function executed across process pool workers.
    Bypasses the GIL by running BeautifulSoup parsing in isolated Python processes.
    
    Payload format: (url, html_content, base_url, allowed_netloc, allowed_base_path, keyword_filter)
    Returns: (url, has_keyword, navigation_links, asset_urls)
    """
    url, html_content, base_url, allowed_netloc, allowed_base_path, keyword_filter = payload
    
    # 1. Inspect text content for keyword match
    has_keyword = HTMLDocumentParser.matches_keyword(html_content, keyword_filter)
    
    # 2. Extract in-scope child navigation links and assets
    nav_links, asset_urls = HTMLDocumentParser.extract_links_and_assets(
        html_content=html_content,
        base_url=base_url,
        allowed_netloc=allowed_netloc,
        allowed_base_path=allowed_base_path
    )
    
    return url, has_keyword, nav_links, asset_urls


class HTMLDocumentParser:
    """
    Dedicated document analysis parser that decouples DOM structural analysis
    from network I/O operations. Uses BeautifulSoup and lxml for high-performance parsing.
    """

    @staticmethod
    def is_high_risk_url(url_str: str) -> bool:
        """Checks if a URL contains high-risk patterns likely to trigger redirect loops."""
        lower_url = url_str.lower()
        return any(pattern in lower_url for pattern in HIGH_RISK_PATTERNS)

    @staticmethod
    def sanitize_url(raw_url: str) -> str:
        """
        Sanitizes and normalizes URL paths using yarl. Proactively enforces trailing 
        slashes on directory endpoints to prevent server-side redirect loops.
        """
        try:
            base_url = raw_url.split("#")[0]
            url_obj = URL(base_url)
            decoded_path = url_obj.path.replace("%2F", "/")
            
            # Enforce trailing slash on directories without extensions
            if not Path(decoded_path).suffix and not decoded_path.endswith("/"):
                decoded_path += "/"
                
            reconstructed = url_obj.with_path(decoded_path).with_query(url_obj.query)
            return str(reconstructed)
        except Exception:
            return raw_url.split("#")[0]

    @staticmethod
    def extract_text_content(html_content: str) -> str:
        """Extracts clean text content from raw HTML for inspection."""
        soup = BeautifulSoup(html_content, "lxml")
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer"]):
            element.decompose()
        return soup.get_text(separator=" ", strip=True)

    @classmethod
    def matches_keyword(cls, html_content: str, keyword: Optional[str]) -> bool:
        """Inspects DOM text content against an optional keyword or phrase."""
        if not keyword:
            return True
        extracted_text = cls.extract_text_content(html_content)
        return keyword.lower() in extracted_text.lower()

    @classmethod
    def extract_links_and_assets(
        cls, 
        html_content: str, 
        base_url: str, 
        allowed_netloc: str, 
        allowed_base_path: str
    ) -> Tuple[List[str], List[str]]:
        """
        Parses HTML content to extract in-scope child navigation links and binary assets.
        
        :return: Tuple of (navigation_links, asset_urls)
        """
        soup = BeautifulSoup(html_content, "lxml")
        navigation_links: List[str] = []
        asset_urls: List[str] = []

        # 1. Parse anchor tags for navigation and downloadable files
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            try:
                absolute_url = URL(base_url).join(URL(href))
                clean_target = cls.sanitize_url(str(absolute_url))

                if cls.is_high_risk_url(clean_target):
                    continue

                parsed_target = URL(clean_target)
                if parsed_target.host == allowed_netloc and parsed_target.path.startswith(allowed_base_path):
                    target_ext = Path(parsed_target.path).suffix.lower()

                    if target_ext in BINARY_EXTENSIONS or "download" in parsed_target.path.lower():
                        if clean_target not in asset_urls:
                            asset_urls.append(clean_target)
                    else:
                        if clean_target not in navigation_links:
                            navigation_links.append(clean_target)
            except Exception:
                continue

        # 2. Parse image tags for visual assets
        for img_tag in soup.find_all("img", src=True):
            src = img_tag["src"].strip()
            if not src or src.startswith("data:"):
                continue

            try:
                absolute_img = URL(base_url).join(URL(src))
                clean_img = cls.sanitize_url(str(absolute_img))

                if cls.is_high_risk_url(clean_img):
                    continue

                parsed_img = URL(clean_img)
                if parsed_img.host == allowed_netloc and parsed_img.path.startswith(allowed_base_path):
                    if clean_img not in asset_urls:
                        asset_urls.append(clean_img)
            except Exception:
                continue

        return navigation_links, asset_urls

    @staticmethod
    async def parse_batch_parallel(
        batch_items: List[Tuple[str, str, str, str, str]], 
        keyword_filter: Optional[str] = None, 
        max_workers: int = 3
    ) -> List[Tuple[str, bool, List[str], List[str]]]:
        """
        Asynchronously maps batch HTML items across Cores 2-4 using a ProcessPoolExecutor.
        Leaves Core 1 free for the asyncio event loop and network requests.
        """
        loop = asyncio.get_running_loop()
        payloads = [
            (url, content, base_url, netloc, base_path, keyword_filter)
            for url, content, base_url, netloc, base_path in batch_items
        ]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                loop.run_in_executor(executor, parse_document_worker, payload)
                for payload in payloads
            ]
            results = await asyncio.gather(*futures)
            
        return results
