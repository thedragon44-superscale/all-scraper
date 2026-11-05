import os
import sys
from pathlib import Path

# Ensure project root is in sys.path to load config settings
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import DATA_DIR

def get_dir_size(path: Path) -> float:
    try:
        total_bytes = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
        return round(total_bytes / (1024 * 1024), 2)
    except Exception:
        return 0.0

def run_verification():
    print("========================================")
    print("       LOCAL STORAGE DIAGNOSTICS        ")
    print("========================================")
    
    if not DATA_DIR.exists():
        print("[!] Warning: DATA_DIR path does not exist yet.")
        return

    try:
        html_files = list(DATA_DIR.glob("**/*.html"))
        asset_extensions = {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".webp", ".gif", ".zip"}
        all_files = [f for f in DATA_DIR.glob("**/*") if f.is_file()]
        asset_files = [f for f in all_files if f.suffix.lower() in asset_extensions]
        
        total_size_mb = get_dir_size(DATA_DIR)
        
        print(f"[+] Data Directory Path:     {DATA_DIR}")
        print(f"[+] Total Disk Footprint:    {total_size_mb} MB")
        print(f"[+] Total Files on Disk:     {len(all_files)}")
        print(f"[+] Cached HTML files:       {len(html_files)}")
        print(f"[+] Cached Assets (Disk):    {len(asset_files)}")
        
        ext_counts = {}
        for ext in asset_extensions:
            cnt = len(list(DATA_DIR.glob(f"**/*{ext}")))
            if cnt > 0:
                ext_counts[ext] = cnt
        if ext_counts:
            print(f"    - Asset Breakdown:       {ext_counts}")

        # Interactive File Content Browser
        print("\n========================================")
        print("       INTERACTIVE FILE BROWSER         ")
        print("========================================")
        inspect_choice = input("Would you like to browse cached files? (y/n): ").strip().lower()
        
        if inspect_choice == 'y':
            while True:
                print("\nOptions:")
                print(" [1] List recent HTML files")
                print(" [2] Search files by keyword")
                print(" [0] Exit Browser")
                
                choice = input("Enter choice (0-2): ").strip()
                if choice == '0':
                    break
                elif choice == '1':
                    limit_str = input("How many files to display? [default 10]: ").strip()
                    limit = int(limit_str) if limit_str.isdigit() else 10
                    
                    sample_files = html_files[:limit]
                    print(f"\n--- Showing first {len(sample_files)} cached HTML files ---")
                    for idx, f_path in enumerate(sample_files, 1):
                        print(f" [{idx}] {f_path.relative_to(DATA_DIR)}")
                    
                    file_idx_str = input("\nEnter file number to view path (or press Enter to skip): ").strip()
                    if file_idx_str.isdigit():
                        f_idx = int(file_idx_str) - 1
                        if 0 <= f_idx < len(sample_files):
                            print(f"\nFull Path: {sample_files[f_idx].resolve()}")
                
                elif choice == '2':
                    keyword = input("Enter search keyword for file paths: ").strip().lower()
                    if keyword:
                        matches = [f for f in all_files if keyword in f.name.lower()]
                        print(f"\nFound {len(matches)} matching files:")
                        for idx, match in enumerate(matches[:15], 1):
                            print(f" {idx}. {match.relative_to(DATA_DIR)}")
                        if len(matches) > 15:
                            print(f" ... and {len(matches) - 15} more matches.")
                
                cont = input("\nPerform another action? (y/n): ").strip().lower()
                if cont != 'y':
                    break
            
    except Exception as e:
        print(f"[!] Verification failed due to an error: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("========================================")

if __name__ == "__main__":
    run_verification()
