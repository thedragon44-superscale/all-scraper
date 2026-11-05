import json
from pathlib import Path
from config import DATA_DIR

HISTORY_FILE = DATA_DIR / "url_history.json"

def load_url_history() -> list[str]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_url_to_history(url: str):
    history = load_url_history()
    # Remove if already exists to push it to the top/recent
    if url in history:
        history.remove(url)
    history.insert(0, url)
    # Keep only the last 10 entries
    history = history[:10]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
