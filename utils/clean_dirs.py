import os
import sys
import traceback
from pathlib import Path
from tqdm import tqdm
from termcolor import colored

# Add backend root to path to load config settings
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import DATA_DIR

def clean_empty_directories():
    print("========================================")
    print(colored("      ROBUST EMPTY DIRECTORY PRUNER     ", "cyan", attrs=["bold"]))
    print("========================================")
    
    if not DATA_DIR.exists():
        print(colored(f"[!] Error: DATA_DIR not found at {DATA_DIR}", "red"))
        return

    empty_dirs_removed = 0
    error_count = 0
    
    # Collect all subdirectories beneath DATA_DIR
    all_dirs = []
    for root, dirs, files in os.walk(DATA_DIR, topdown=False):
        root_path = Path(root)
        if root_path != DATA_DIR:
            all_dirs.append(root_path)

    print(colored(f"[*] Scanning {len(all_dirs)} directories for nested empty folders...", "yellow"))
    
    # Bottom-up traversal via tqdm progress bar
    for root_path in tqdm(all_dirs, desc=colored("Pruning Folders", "blue")):
        try:
            # Check if directory is completely empty (no files, no subfolders)
            if not any(root_path.iterdir()):
                root_path.rmdir()
                empty_dirs_removed += 1
        except Exception as e:
            error_count += 1
            print(colored(f"\n[!] Failed to remove folder {root_path.relative_to(DATA_DIR)}: {e}", "red"))
            traceback.print_exc()

    print("========================================")
    print(colored("            PRUNING SUMMARY             ", "cyan", attrs=["bold"]))
    print("========================================")
    print(f"  - Empty Folders Removed: {colored(str(empty_dirs_removed), 'green')}")
    print(f"  - Errors Encountered:    {colored(str(error_count), 'red' if error_count > 0 else 'green')}")
    print("========================================")

if __name__ == "__main__":
    clean_empty_directories()
