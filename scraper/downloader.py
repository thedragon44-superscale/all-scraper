import asyncio
import aiohttp
from pathlib import Path
from tqdm.asyncio import tqdm
from config import DATA_DIR, HEADERS, REQUEST_TIMEOUT
from utils import URLUtils, handle_download_exceptions

class UniversalDownloader:
    def __init__(self, max_concurrent: int = 3):
        """
        Initializes the universal async downloader with lazy-initialized 
        event-loop-dependent objects to prevent startup errors.
        """
        self.max_concurrent = max_concurrent
        self._semaphore = None
        self._connector = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Lazy-initializes the asyncio Semaphore bound to the active event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    @property
    def connector(self) -> aiohttp.TCPConnector:
        """
        Lazy-initializes a custom aiohttp TCPConnector with connection pooling limits 
        and DNS caching optimization.
        """
        if self._connector is None or self._connector.closed:
            self._connector = aiohttp.TCPConnector(
                limit=15,
                limit_per_host=8,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
        return self._connector

    @handle_download_exceptions
    async def download_page(self, session: aiohttp.ClientSession, url: str, relative_path: str) -> tuple[str, Path] | None:
        """
        Asynchronously downloads a single file, resource, or network-intercepted stream and caches it locally,
        with automatic retries, exponential backoff for gateway errors, content-type extension correction, and centralized URL sanitization.
        """
        clean_url = URLUtils.sanitize_url(url)
        file_path = DATA_DIR / relative_path
        
        # Return early if already cached locally and not empty
        if file_path.exists() and file_path.stat().st_size > 0:
            return (clean_url, file_path)

        # Prevent file system collisions if a directory path matches a target file name
        if file_path.is_dir():
            file_path = file_path / "index.html"

        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with self.semaphore:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    # Polite micro-delay between requests
                    await asyncio.sleep(0.3 * attempt)
                    
                    async with session.get(clean_url, headers=HEADERS, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as response:
                        if response.status == 200:
                            content_type = response.headers.get("Content-Type", "").lower()
                            
                            # Map MIME types to correct file extensions to prevent binary streams saving as .html
                            ext_mapping = {
                                "image/webp": ".webp",
                                "image/jpeg": ".jpg",
                                "image/png": ".png",
                                "image/gif": ".gif",
                                "image/svg+xml": ".svg",
                                "application/pdf": ".pdf",
                                "application/zip": ".zip",
                            }
                            
                            is_binary = any(t in content_type for t in ["application/pdf", "image/", "application/octet-stream", "application/zip", "image/svg+xml"])
                            
                            # Dynamically correct file extension based on response Content-Type
                            matched_ext = next((ext for mime, ext in ext_mapping.items() if mime in content_type), None)
                            if matched_ext:
                                if file_path.suffix.lower() != matched_ext:
                                    file_path = file_path.with_suffix(matched_ext)
                                    file_path.parent.mkdir(parents=True, exist_ok=True)
                                is_binary = True

                            binary_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".zip", ".ico"}
                            if not content_type or file_path.suffix.lower() in binary_extensions:
                                is_binary = file_path.suffix.lower() in binary_extensions or is_binary

                            if is_binary:
                                content = await response.read()
                                file_path.write_bytes(content)
                            else:
                                # Validate suffix against whitelist; replace false suffixes with .html
                                valid_extensions = {".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".zip", ".ico"}
                                if file_path.suffix.lower() not in valid_extensions:
                                    file_path = file_path.with_suffix(".html")
                                    file_path.parent.mkdir(parents=True, exist_ok=True)
                                    
                                content = await response.text(errors="ignore")
                                file_path.write_text(content, encoding="utf-8")
                            
                            return (clean_url, file_path)
                            
                        elif response.status == 404:
                            return None
                            
                        elif response.status in [502, 503, 504]:
                            # Gateway errors - retry with exponential backoff if attempts remain
                            if attempt < max_retries:
                                await asyncio.sleep(1.5 * attempt)
                                continue
                            return None
                        else:
                            return None
                            
                except aiohttp.TooManyRedirects:
                    return None
                    
                except Exception as e:
                    if attempt < max_retries:
                        await asyncio.sleep(1.5 * attempt)
                        continue
                    raise
                    
            return None

    async def download_batch(self, urls_and_paths: list[tuple[str, str]]) -> list[tuple[str, Path]]:
        """Downloads a batch of URLs concurrently using the optimized TCP connector and a visual progress bar."""
        async with aiohttp.ClientSession(connector=self.connector) as session:
            tasks = [
                self.download_page(session, url, path) 
                for url, path in urls_and_paths
            ]
            results = await tqdm.gather(*tasks, desc="[↓] Downloading Files")
            return [res for res in results if res is not None]
