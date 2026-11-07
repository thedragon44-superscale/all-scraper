import os
from pathlib import Path
import collections
from typing import Any

class CaseInsensitiveDict(collections.UserDict[str | bytes, Any]):
    """
    A dict-like structure that accepts strings or bytes as keys and allows 
    case-insensitive lookups, preventing header collision and lookup failures.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._keys: dict[str | bytes, Any] = {}
        super().__init__(*args, **kwargs)

    def __getitem__(self, key: str | bytes) -> Any:
        normalized_key = self._normkey(key)
        return super().__getitem__(self._keys[normalized_key.lower()])

    def __setitem__(self, key: str | bytes, value: Any) -> None:
        normalized_key = self._normkey(key)
        try:
            lower_key = self._keys[normalized_key.lower()]
            del self[lower_key]
        except KeyError:
            pass
        super().__setitem__(normalized_key, self._normvalue(value))
        self._keys[normalized_key.lower()] = normalized_key

    def __delitem__(self, key: str | bytes) -> None:
        normalized_key = self._normkey(key)
        stored_key = self._keys.pop(normalized_key.lower())
        super().__delitem__(stored_key)

    def __contains__(self, key: str | bytes) -> bool:
        normalized_key = self._normkey(key)
        return normalized_key.lower() in self._keys

    def _normkey(self, key: str | bytes) -> str | bytes:
        if isinstance(key, bytes):
            return key.decode("utf-8", errors="replace")
        return key

    def _normvalue(self, value: Any) -> Any:
        return value

# Base Directories (with environment fallback support)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SCRAPE_DATA_DIR", BASE_DIR / "data"))
LOGS_DIR = Path(os.getenv("SCRAPE_LOGS_DIR", BASE_DIR / "logs"))

# Ensure local directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Global Network & Scraping Constraints (Target-agnostic with env overrides)
REQUEST_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", 120))
REQUEST_DELAY = float(os.getenv("SCRAPE_DELAY", 1.5))
MAX_CONCURRENT_DEFAULT = int(os.getenv("SCRAPE_MAX_CONCURRENT", 3))

# HTTP Headers utilizing case-insensitive mapping to prevent header collision
HEADERS = CaseInsensitiveDict({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})
