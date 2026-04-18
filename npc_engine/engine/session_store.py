"""Async-safe session store with TTL eviction.

SessionStore
------------
- ``get(key)``                  → dict | None  (None when missing or expired)
- ``set(key, data)``            → None
- ``get_or_create(key, default)`` → dict       (existing entry or newly-created default)
- ``sweep_expired()``           → int          (count of entries removed)
- ``__len__()``                 → int

All mutating operations acquire a single ``asyncio.Lock`` so concurrent
FastAPI handler coroutines never corrupt the store.  The lock is
*not* held across external I/O — only dict mutations.

Eviction policy
---------------
- Entries are lazily expired on ``get`` / ``get_or_create``.
- When ``max_sessions`` is reached a new ``set`` evicts the oldest
  (insertion-order) entry before writing, keeping size bounded.
- ``sweep_expired`` proactively removes all stale entries in one pass;
  call it from a background task / startup sweep if needed.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional


class SessionStore:
    """Async-safe TTL session store backed by an insertion-order dict."""

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        max_sessions: int = 10_000,
    ) -> None:
        # values: (session_data, last_touch_monotonic)
        self._store: dict[str, tuple[Dict[str, Any], float]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return session data, or None if missing / expired."""
        async with self._lock:
            return self._get_unlocked(key)

    async def set(self, key: str, data: Dict[str, Any]) -> None:
        """Store session data, evicting the oldest entry if at capacity."""
        async with self._lock:
            self._evict_if_full(key)
            self._store[key] = (data, time.monotonic())

    async def get_or_create(
        self,
        key: str,
        default: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the existing live session or create one from *default*.

        The returned dict is the *same object* stored in the store —
        callers that mutate it must call ``set`` afterwards to bump the
        touch timestamp and persist changes.
        """
        async with self._lock:
            existing = self._get_unlocked(key)
            if existing is not None:
                return existing
            # Create new entry
            self._evict_if_full(key)
            self._store[key] = (default, time.monotonic())
            return default

    async def sweep_expired(self) -> int:
        """Remove all expired entries in one pass.  Returns count removed."""
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, (_, ts) in self._store.items() if now - ts > self.ttl]
            for k in expired:
                del self._store[k]
            return len(expired)

    def __len__(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Private helpers (must be called while lock is held)
    # ------------------------------------------------------------------

    def _get_unlocked(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(key)
        if entry is None:
            return None
        data, ts = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            return None
        # Refresh touch time on every successful read
        self._store[key] = (data, time.monotonic())
        return data

    def _evict_if_full(self, incoming_key: str) -> None:
        """Evict the oldest entry when at capacity (only if key is new)."""
        if incoming_key in self._store:
            return  # update in-place — no eviction needed
        if len(self._store) >= self.max_sessions:
            oldest = next(iter(self._store))
            del self._store[oldest]
