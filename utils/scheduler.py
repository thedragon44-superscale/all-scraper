import asyncio
from typing import Optional, Set, Tuple
from utils.url import URLUtils

class RequestScheduler:
    """
    Centralized request queue and deduplication filter layer that prioritizes 
    manifest/index processing over individual assets or tiles.
    """
    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._visited: Set[str] = set()
        self._counter = 0

    def is_visited(self, url: str) -> bool:
        """Checks if a URL has already been visited or queued."""
        clean = URLUtils.sanitize_url(url)
        return clean in self._visited

    def mark_visited(self, url: str):
        """Marks a URL fingerprint as visited."""
        clean = URLUtils.sanitize_url(url)
        self._visited.add(clean)

    async def push(self, url: str, priority: int = 1, metadata: Optional[dict] = None) -> bool:
        """
        Pushes a URL into the priority queue if not already visited.
        Lower priority integer means higher priority (e.g., 0 for manifests/indexes, 
        1 for standard pages, 2 for binary assets/tiles).
        """
        clean = URLUtils.sanitize_url(url)
        if clean in self._visited:
            return False

        self._visited.add(clean)
        self._counter += 1
        
        # Priority tuple: (priority_level, insertion_counter, url, metadata)
        # Insertion counter ensures FIFO ordering for items sharing the same priority level.
        await self._queue.put((priority, self._counter, clean, metadata or {}))
        return True

    async def get(self) -> Tuple[int, str, dict]:
        """
        Retrieves the next highest-priority item from the queue.
        Returns a tuple of (priority, url, metadata).
        """
        priority, _, url, metadata = await self._queue.get()
        return priority, url, metadata

    def task_done(self):
        """Indicates that a formerly enqueued task is complete."""
        self._queue.task_done()

    def qsize(self) -> int:
        """Returns approximate size of the queue."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Returns True if the queue is empty."""
        return self._queue.empty()
