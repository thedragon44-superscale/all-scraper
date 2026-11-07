from collections.abc import MutableMapping
from collections import OrderedDict

class CaseInsensitiveDict(MutableMapping):
    """
    A case-insensitive dictionary for uniform header and key management.
    """
    def __init__(self, data=None, **kwargs):
        self._store = OrderedDict()
        if data:
            self.update(data)
        if kwargs:
            self.update(kwargs)

    def __setitem__(self, key, value):
        self._store[key.lower()] = (key, value)

    def __getitem__(self, key):
        return self._store[key.lower()][1]

    def __delitem__(self, key):
        del self._store[key.lower()]

    def __iter__(self):
        return (casedkey for casedkey, mappedvalue in self._store.values())

    def __len__(self):
        return len(self._store)

    def lower_items(self):
        return ((lowerkey, mappedvalue[1]) for lowerkey, mappedvalue in self._store.items())

    def __repr__(self):
        return f"{dict(self.items())}"


class LocalCache:
    """
    A size-limited local cache for memoization, caching, and deduplication.
    """
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache = OrderedDict()

    def __contains__(self, key):
        return key in self._cache

    def get(self, key, default=None):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return default

    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)
