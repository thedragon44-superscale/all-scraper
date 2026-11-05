import os
import sys
import shutil
import traceback
from pathlib import Path
from termcolor import colored

# Ensure project root is in sys.path so modules resolve cleanly
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DATA_DIR

def reset_system():
    print("========================================")
    print(colored("          SYSTEM DATA RESET             ", "red", attrs=["bold"]))
    print("========================================")
    print(colored("[!] WARNING: This will completely wipe all cached", "yellow"))
    print(colored("    HTML files, documents, and local assets!", "yellow"))
    print("----------------------------------------")
    
    confirm = input(colored("Are you sure you want to proceed? (yes/N): ", "cyan")).strip().lower()
    if confirm != "yes":
        print("[*] Reset aborted by user. Returning to safety.")
        return

    # Purge DATA_DIR
    print("\n[*] Purging local data directory...")
    try:
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
            print(colored(f"  [+] Successfully removed directory tree: {DATA_DIR}", "green"))
        
        # Recreate empty root and assets folder
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "assets").mkdir(parents=True, exist_ok=True)
        print(colored("  [+] Recreated fresh, empty data and assets directories.", "green"))
    except Exception as e:
        print(colored(f"  [!] Error wiping data directory: {e}", "red"))
        traceback.print_exc()

    print("========================================")
    print(colored("     SYSTEM RESET COMPLETE & PRISTINE   ", "green", attrs=["bold"]))
    print("========================================")

if __name__ == "__main__":
    try:
        reset_system()
    except KeyboardInterrupt:
        print("\n\n[*] Reset interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as err:
        print(colored(f"\n[!] FATAL RESET EXCEPTION: {err}", "red"))
        traceback.print_exc()
        sys.exit(1)
