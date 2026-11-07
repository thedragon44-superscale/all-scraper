import os
import argparse
from pathlib import Path
from urllib.parse import urlparse
from yarl import URL
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from config.settings import DATA_DIR, HEADERS
from utils import URLUtils

def harvest_assets(base_url: str = ""):
    """
    Scans local HTML files in the data directory, discovers embedded images and assets,
    and downloads them locally with automatic base URL inference and centralized URL sanitization.
    """
    print("========================================")
    print("      UNIVERSAL ASSET HARVESTER         ")
    print("========================================")
    
    assets_dir = DATA_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    html_files = list(DATA_DIR.glob("**/*.html"))
    print(f"[*] Scanning {len(html_files)} local HTML files for assets...")
    
    # Comprehensive Diagnostic Counters
    stats = {
        "total_links_found": 0,
        "filtered_out": 0,
        "already_cached": 0,
        "newly_downloaded": 0,
        "download_errors": 0
    }
    
    error_log_samples = []
    valid_extensions = {".png", ".jpg", ".jpeg", ".pdf", ".gif", ".webp", ".svg", ".ico"}
    
    for file_path in tqdm(html_files, desc="[+] Harvesting Assets"):
        try:
            if not file_path.exists():
                continue
            
            html_content = file_path.read_text(encoding="utf-8", errors="ignore")
            # Switched to 'lxml' parser for speed and consistency with parser modules
            soup = BeautifulSoup(html_content, "lxml")
            
            # Auto-detect base URL from file metadata if not explicitly provided
            file_base_url = base_url
            if not file_base_url:
                base_tag = soup.find("base", href=True)
                if base_tag:
                    file_base_url = base_tag["href"]
                else:
                    canonical = soup.find("link", rel="canonical")
                    if canonical and canonical.get("href"):
                        file_base_url = canonical["href"]
                    else:
                        for tag in soup.find_all(["a", "img"], href=True) or soup.find_all("img", src=True):
                            link = tag.get("href") or tag.get("src")
                            if link and link.startswith("http"):
                                parsed_link = URL(link)
                                file_base_url = f"{parsed_link.scheme}://{parsed_link.host}"
                                break
            
            asset_urls = set()
            
            # 1. Target <img> tags and media attributes specifically
            for img in soup.find_all("img"):
                for attr in ["src", "data-src", "data-original", "data-lazy-src", "srcset"]:
                    val = img.get(attr)
                    if val:
                        first_url = val.split(",")[0].split(" ")[0].strip()
                        if first_url:
                            asset_urls.add(first_url)
                            
            # 2. Target <a> anchor tags ONLY if the href explicitly ends with a valid asset extension
            for a in soup.find_all("a"):
                href = a.get("href")
                if href:
                    clean_href = href.strip().split("?")[0]
                    if any(clean_href.lower().endswith(ext) for ext in valid_extensions):
                        asset_urls.add(href.strip())
            
            for raw_url in asset_urls:
                stats["total_links_found"] += 1
                try:
                    # Exclude site navigation UI icons, JavaScript hooks, or data URIs
                    if "/icons/" in raw_url or raw_url.startswith("javascript:") or raw_url.startswith("data:"):
                        stats["filtered_out"] += 1
                        continue
                        
                    # Reconstruct full absolute URL using yarl for robust relative path resolution
                    if not raw_url.startswith("http"):
                        if file_base_url:
                            target_url = str(URL(file_base_url).join(URL(raw_url)))
                        else:
                            stats["download_errors"] += 1
                            if len(error_log_samples) < 10:
                                error_log_samples.append(f"MissingSchema (No base URL for relative link): {raw_url}")
                            continue
                    else:
                        target_url = raw_url
                        
                    # Centralized sanitization to clean up fragments or redundant queries
                    target_url = URLUtils.sanitize_url(target_url)
                        
                    parsed_url = urlparse(target_url)
                    filename = os.path.basename(parsed_url.path)
                    if not filename:
                        stats["filtered_out"] += 1
                        continue
                        
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in valid_extensions:
                        stats["filtered_out"] += 1
                        continue
                        
                    dest_path = assets_dir / filename
                    
                    # Check cache status
                    if dest_path.exists() and dest_path.stat().st_size > 0:
                        stats["already_cached"] += 1
                        continue
                        
                    # Attempt network download
                    try:
                        resp = requests.get(target_url, headers=HEADERS, timeout=15)
                        if resp.status_code == 200:
                            dest_path.write_bytes(resp.content)
                            stats["newly_downloaded"] += 1
                        else:
                            stats["download_errors"] += 1
                            if len(error_log_samples) < 10:
                                error_log_samples.append(f"HTTP {resp.status_code}: {target_url}")
                    except Exception as net_err:
                        stats["download_errors"] += 1
                        if len(error_log_samples) < 10:
                            error_log_samples.append(f"{type(net_err).__name__} ({net_err}): {target_url}")
                        continue
                        
                except Exception as link_err:
                    stats["download_errors"] += 1
                    continue
                    
        except Exception as art_err:
            continue
            
    print("\n========================================")
    print("          ASSET HARVESTER REPORT        ")
    print("========================================")
    print(f"  - Total Asset Links Discovered:   {stats['total_links_found']}")
    print(f"  - Filtered Out (UI/Non-Asset):    {stats['filtered_out']}")
    print(f"  - Already Cached Locally (Disk):  {stats['already_cached']}")
    print(f"  - Newly Downloaded Files:         {stats['newly_downloaded']}")
    print(f"  - Download Errors Encountered:    {stats['download_errors']}")
    
    if error_log_samples:
        print("\n----------------------------------------")
        print("        SAMPLE DOWNLOAD FAILURES        ")
        print("----------------------------------------")
        for err_sample in error_log_samples:
            print(f"  [!] {err_sample}")
    print("========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Asset Harvester")
    parser.add_argument("--base-url", type=str, default="", help="Base URL for resolving relative asset links (e.g. https://charm.li/)")
    args = parser.parse_args()
    harvest_assets(base_url=args.base_url)
