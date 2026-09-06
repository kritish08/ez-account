"""A small in-process rate limiter.

Used to put a brake on the endpoints that were previously unbounded:
password login (credential stuffing), the invoice-image parser and the
voice socket (both of which spend money per call).

Deliberately in-process. This app deploys as a single backend container,
and the factory-reset cooldown already worked this way. If it is ever
scaled horizontally these counters become per-replica, which weakens the
limit proportionally — that is the point at which this should move to
Redis, not before.

The window is a sliding one: a key's attempt timestamps are kept, stale
ones are dropped on read, and the key is blocked while `max_attempts`
timestamps remain inside `window_seconds`. A slow trickle of failures
therefore never accumulates into a lockout.
"""

import time
from collections import deque


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float, clock=time.time):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque] = {}

    def _prune(self, key: str, now: float) -> deque:
        bucket = self._attempts.get(key)
        if bucket is None:
            return deque()
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            # Drop the key entirely so a caller cycling keys (one per
            # guessed email, say) cannot grow this map without bound.
            self._attempts.pop(key, None)
        return bucket

    def _sweep(self, now: float) -> None:
        """Drop every key whose attempts have all aged out."""
        for key in list(self._attempts):
            self._prune(key, now)

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again. 0 means allowed now."""
        now = self._clock()
        bucket = self._prune(key, now)
        if len(bucket) < self.max_attempts:
            return 0
        # Blocked until the oldest attempt in the window ages out.
        return max(1, int(round(bucket[0] + self.window_seconds - now)))

    def record(self, key: str) -> None:
        """Count one attempt against `key`."""
        now = self._clock()
        # Amortised cleanup: sweeping on write keeps the map bounded without
        # needing a background task.
        self._sweep(now)
        self._attempts.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        """Forget `key`'s attempts — e.g. after a successful login."""
        self._attempts.pop(key, None)
