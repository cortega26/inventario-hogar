import threading
import time
from typing import Any, Dict, Optional, Tuple

from .config import AppConfig


class Cache:
    """Simple time-based cache implementation."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if expiry > time.time():
                    return value
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            ttl_value = AppConfig.CACHE_TTL if ttl is None else ttl
            self._cache[key] = (value, time.time() + ttl_value)

            if len(self._cache) > AppConfig.MAX_CACHE_SIZE:
                current_time = time.time()
                self._cache = {
                    k: v for k, v in self._cache.items() if v[1] > current_time
                }

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is not None:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all cached entries whose key starts with the given prefix."""
        with self._lock:
            keys_to_delete = [key for key in self._cache if key.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
