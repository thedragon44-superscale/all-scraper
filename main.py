import sys
import argparse
import traceback
from pathlib import Path

# Ensure project root is in sys.path so modules resolve cleanly
sys.path.append(str(Path(__file__).resolve().parent))

from config import DATA_DIR, MAX_CONCURRENT_DEFAULT
from utils.dispatch import ScraperDispatcher
from parser.image_parser import harvest_assets
from utils.verify_data import run_verification
from utils.history import load_url_history, save_url_to_history
from utils.clean_dirs import clean_empty_directories
from utils.reset_system import reset_system
from utils.stitch_pdf import stitch_images_to_pdf
from utils import URLUtils


PROFILE_CHOICES = [
    "auto",
    "hierarchical",
    "flat_paged",
    "asset_index",
    "sitemap",
    "feed",
    "headless",
    "infinite_scroll",
    "authenticated",
    "openapi",
    "universal"
]

BRANCH_PROMPT_CHOICES = ["all", "first", "every", "none"]


def get_target_url() -> str:
    """Presents an interactive menu of recent targets or accepts a new URL."""
    history = load_url_history()
    
    print("\n========================================")
    print("      UNIVERSAL SCRAPER ENGINE          ")
    print("========================================")
    
    if history:
        print("\nRecent Targets:")
        for idx, cached_url in enumerate(history, 1):
            print(f"  [{idx}] {cached_url}")
        print("  [0] Enter a brand new URL")
        
        choice = input("\nSelect an option (number) or paste a new URL: ").strip()
        
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(history):
                selected = history[idx - 1]
                sanitized_selected = URLUtils.sanitize_url(selected)
                print(f"[*] Using cached target: {sanitized_selected}")
                return sanitized_selected
        elif choice.startswith("http"):
            sanitized_choice = URLUtils.sanitize_url(choice)
            save_url_to_history(sanitized_choice)
            return sanitized_choice

    new_url = input("\nEnter target BASE_URL: ").strip()
    if new_url:
        sanitized_new = URLUtils.sanitize_url(new_url)
        save_url_to_history(sanitized_new)
        return sanitized_new
    return new_url


def run_scraper_flow(
    forced_profile: str = None, 
    concurrency: int = MAX_CONCURRENT_DEFAULT, 
    url: str = None, 
    keyword_filter: str = None,
    branch_prompt: str = "first",
    non_interactive: bool = False
):
    """Handles target selection and dispatches the multi-crawler pipeline with full parameter wiring and centralized URL sanitization."""
    raw_target = url or get_target_url()
    if not raw_target:
        print("[!] No target URL specified. Returning to main menu.")
        return

    target_url = URLUtils.sanitize_url(raw_target)

    if forced_profile == "auto":
        forced_profile = None

    if not keyword_filter and not non_interactive:
        kw_input = input("Enter optional keyword or phrase filter (Press Enter to skip): ").strip()
        if kw_input:
            keyword_filter = kw_input

    print(f"\n[*] Initializing Scraper Dispatcher for: {target_url}")
    print(f"[*] Concurrency Limit: {concurrency}")
    print(f"[*] Branch Prompt Strategy: {branch_prompt}")
    if non_interactive:
        print(f"[*] Non-Interactive Flag Active: Skipping interactive prompts.")
    if keyword_filter:
        print(f"[*] Keyword Filter Active: \"{keyword_filter}\"")

    try:
        dispatcher = ScraperDispatcher(max_concurrent=concurrency)
        dispatcher.run(
            target_url, 
            forced_profile=forced_profile, 
            keyword_filter=keyword_filter,
            non_interactive=non_interactive
        )
    except Exception as e:
        print(f"\n[!] CRITICAL SCRAPER FAILURE: {type(e).__name__} - {e}")
        print("----------------------------------------")
        traceback.print_exc()
        print("----------------------------------------\n")


def interactive_menu():
    """Presents an interactive menu hub as the default entry point."""
    while True:
        print("\n========================================")
        print("      UNIVERSAL SCRAPER PIPELINE HUB    ")
        print("========================================")
        print(" [1] Scrape Target Website (Smart Dispatcher & Multi-Crawler)")
        print(" [2] Harvest Local Assets & Images")
        print(" [3] Stitch Downloaded Tiles into PDF")
        print(" [4] Run Local Storage Diagnostics")
        print(" [5] Clean Empty Nested Directories")
        print(" [6] Full System Reset (Wipe Data Directory)")
        print(" [7] Exit")
        print("----------------------------------------")
        
        choice = input("Select an option (1-7): ").strip()
        
        if choice == "1":
            run_scraper_flow()
            
        elif choice == "2":
            base_url = input("Enter base URL for resolving relative assets (optional, press Enter to skip): ").strip()
            if base_url:
                base_url = URLUtils.sanitize_url(base_url)
            print("\n[*] Starting universal asset harvester...")
            try:
                harvest_assets(base_url=base_url)
            except Exception as e:
                print(f"\n[!] ERROR in Asset Harvester: {type(e).__name__} - {e}")
                traceback.print_exc()

        elif choice == "3":
            print("\n[*] Running PDF Stitcher Utility...")
            try:
                stitch_images_to_pdf()
            except Exception as e:
                print(f"\n[!] ERROR in PDF Stitcher: {type(e).__name__} - {e}")
                traceback.print_exc()
            
        elif choice == "4":
            print("\n[*] Running local storage diagnostics verifier...")
            try:
                run_verification()
            except Exception as e:
                print(f"\n[!] ERROR in Verification Diagnostics: {type(e).__name__} - {e}")
                traceback.print_exc()
                
        elif choice == "5":
            print("\n[*] Running empty directory cleanup utility...")
            try:
                clean_empty_directories()
            except Exception as e:
                print(f"\n[!] ERROR in Directory Cleaner: {type(e).__name__} - {e}")
                traceback.print_exc()

        elif choice == "6":
            print("\n[*] Running system reset utility...")
            try:
                reset_system()
            except Exception as e:
                print(f"\n[!] ERROR in System Reset: {type(e).__name__} - {e}")
                traceback.print_exc()
                
        elif choice == "7":
            print("[*] Exiting pipeline hub. Goodbye!")
            sys.exit(0)
            
        else:
            print("[!] Invalid choice. Please enter a number between 1 and 7.")


def main():
    parser = argparse.ArgumentParser(description="Universal Multi-Crawler Scraper Pipeline Master Hub")
    parser.add_argument("url", type=str, nargs="?", default=None, help="The target start URL to scrape (optional)")
    parser.add_argument("--scrape", action="store_true", help="Run the universal web scraper module")
    parser.add_argument(
        "--profile", 
        type=str, 
        choices=PROFILE_CHOICES,
        default="auto",
        help="Force a specific crawler profile override or use automated fingerprinting (default: auto)"
    )
    parser.add_argument(
        "--branch-prompt",
        type=str,
        choices=BRANCH_PROMPT_CHOICES,
        default="first",
        help="Granularity for interactive tier branch scoping prompts: 'all', 'first' (default), 'every', or 'none'"
    )
    parser.add_argument(
        "--yes", "-y", "--non-interactive",
        action="store_true",
        dest="non_interactive",
        help="Skip all interactive prompts and automatically select recommended choices (for cron or automated use)"
    )
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENT_DEFAULT, help=f"Max concurrent asynchronous downloads (default: {MAX_CONCURRENT_DEFAULT})")
    parser.add_argument("--keyword", type=str, default=None, help="Optional keyword or phrase filter for text content inspection")
    parser.add_argument("--parse-images", action="store_true", help="Run asset harvesting on local HTML files")
    parser.add_argument("--base-url", type=str, default="", help="Base URL for resolving relative asset links")
    parser.add_argument("--stitch-pdf", action="store_true", help="Stitch downloaded page tiles into a master PDF")
    parser.add_argument("--verify", action="store_true", help="Run local storage and file diagnostics")
    parser.add_argument("--reset-system", action="store_true", help="Wipe local data and asset directories")
    parser.add_argument("--clean-dirs", action="store_true", help="Prune empty nested skeleton directories")
    
    args = parser.parse_args()

    # Handle direct CLI calls if flags are passed, otherwise default to interactive hub
    if args.url or args.scrape:
        profile = None if args.profile == "auto" else args.profile
        sanitized_cli_url = URLUtils.sanitize_url(args.url) if args.url else None
        run_scraper_flow(
            forced_profile=profile, 
            concurrency=args.concurrency, 
            url=sanitized_cli_url, 
            keyword_filter=args.keyword,
            branch_prompt=args.branch_prompt,
            non_interactive=args.non_interactive
        )
    elif args.parse_images:
        sanitized_base_url = URLUtils.sanitize_url(args.base_url) if args.base_url else ""
        harvest_assets(base_url=sanitized_base_url)
    elif args.stitch_pdf:
        stitch_images_to_pdf()
    elif args.verify:
        run_verification()
    elif args.reset_system:
        reset_system()
    elif args.clean_dirs:
        clean_empty_directories()
    else:
        interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[*] Process interrupted by user. Exiting cleanly...")
        sys.exit(0)
    except Exception as fatal_err:
        print(f"\n[!] FATAL UNHANDLED PIPELINE EXCEPTION: {fatal_err}")
        print("----------------------------------------")
        traceback.print_exc()
        print("----------------------------------------")
        sys.exit(1)
