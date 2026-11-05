import asyncio
import json
from pathlib import Path
from yarl import URL
from config import DATA_DIR, ScrapingRules
from scraper.downloader import UniversalDownloader
from .base import BaseCrawler

class OpenApiSwaggerCrawler(BaseCrawler):
    def __init__(self, max_concurrent: int = 3, keyword_filter: str = None):
        """
        Specialized crawler targeting OpenAPI and Swagger specification endpoints 
        to automatically parse API routes, parameters, schemas, and keyword filtering.
        """
        super().__init__(name="OpenApiSwaggerCrawler", max_concurrent=max_concurrent, keyword_filter=keyword_filter)
        self.downloader = UniversalDownloader(max_concurrent=max_concurrent)
        self.output_dir = DATA_DIR / "api_specs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl_async(self, start_url: str):
        sanitized_start = self._sanitize_url(start_url)
        parsed_base = URL(sanitized_start)

        print(f"[*] OpenApiSwaggerCrawler active for: {sanitized_start}")

        # Construct common OpenAPI / Swagger specification endpoint candidates
        spec_candidates = [
            sanitized_start if parsed_base.path.endswith(('.json', '.yaml', '.yml')) else None,
            str(parsed_base.with_path("/swagger.json")),
            str(parsed_base.with_path("/openapi.json")),
            str(parsed_base.with_path("/api-docs")),
            str(parsed_base.with_path("/swagger/v1/swagger.json")),
            str(parsed_base.with_path("/swagger/v1/swagger.yaml")),
        ]
        spec_candidates = [c for c in spec_candidates if c]

        print(f"[*] Probing {len(spec_candidates)} potential OpenAPI/Swagger specification endpoints...")

        download_pairs = []
        for url in spec_candidates:
            file_name = URL(url).path.strip("/").replace("/", "_")
            if not file_name:
                file_name = "swagger_spec.json"
            download_pairs.append((url, self.output_dir / file_name))

        results = await self.downloader.download_batch(download_pairs)

        spec_found = False
        for url, saved_file in results:
            if saved_file and saved_file.exists() and saved_file.stat().st_size > 0:
                try:
                    content = saved_file.read_text(encoding="utf-8", errors="ignore")
                    
                    # Evaluate keyword filter across spec content if set
                    if not self._matches_keyword(content):
                        continue

                    # Parse JSON specification schema
                    spec_data = json.loads(content)
                    spec_found = True
                    
                    print(f"\n[+] Successfully parsed OpenAPI specification from: {url}")
                    
                    info = spec_data.get("info", {})
                    print(f"    - API Title: {info.get('title', 'Unknown API')}")
                    print(f"    - Version: {info.get('version', 'N/A')}")
                    
                    paths = spec_data.get("paths", {})
                    print(f"    - Discovered Endpoints: {len(paths)}")
                    
                    # Print a sample preview of endpoints
                    for idx, (path_key, methods) in enumerate(list(paths.items())[:10], 1):
                        method_list = ", ".join(methods.keys()).upper()
                        print(f"      [{idx}] {method_list} {path_key}")
                        self.log_discovery(f"{path_key} [{method_list}]", item_type="page")
                    if len(paths) > 10:
                        print(f"      ... and {len(paths) - 10} more endpoints.")
                        
                    # Generate and save a clean text summary of all routes
                    summary_path = self.output_dir / "parsed_endpoints_summary.txt"
                    summary_lines = [f"{method.upper()} {path}" for path, methods in paths.items() for method in methods.keys()]
                    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
                    print(f"[*] Saved full endpoint summary map to: {summary_path}")
                    break
                    
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"    [!] Error processing spec file from {url}: {e}")

        if not spec_found:
            print("[!] No valid OpenAPI/Swagger JSON specifications matched the criteria at probed paths.")

        print("[*] OpenAPI/Swagger crawl and analysis complete!")

    def crawl(self, start_url: str):
        """Synchronous wrapper for execution."""
        asyncio.run(self.crawl_async(start_url))
