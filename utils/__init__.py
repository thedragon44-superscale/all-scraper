from .history import load_url_history, save_url_to_history
from .clean_dirs import clean_empty_directories
from .dispatch import ScraperDispatcher

__all__ = [
    "load_url_history", 
    "save_url_to_history", 
    "clean_empty_directories",
    "ScraperDispatcher"
]
