"""The shared rate limiter.

Pure logic with an injectable clock, so the behaviour is pinned without
sleeping in tests.
"""

import pytest

from app.services.rate_limit import RateLimiter


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_allows_attempts_up_to_the_limit():
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert limiter.retry_after("user-1") == 0
        limiter.record("user-1")


def test_blocks_once_the_limit_is_reached():
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=3, window_seconds=60, clock=clock)

    for _ in range(3):
        limiter.record("user-1")

    assert limiter.retry_after("user-1") > 0


def test_keys_are_independent():
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)

    limiter.record("user-1")
    limiter.record("user-1")

    assert limiter.retry_after("user-1") > 0
    assert limiter.retry_after("user-2") == 0


def test_window_expires():
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)

    limiter.record("user-1")
    limiter.record("user-1")
    assert limiter.retry_after("user-1") > 0

    clock.advance(61)
    assert limiter.retry_after("user-1") == 0


def test_retry_after_counts_down_from_the_oldest_attempt():
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=1, window_seconds=60, clock=clock)

    limiter.record("user-1")
    assert limiter.retry_after("user-1") == 60

    clock.advance(25)
    assert limiter.retry_after("user-1") == 35


def test_reset_clears_a_key():
    """A successful login must clear the failure count for that account."""
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)

    limiter.record("user-1")
    limiter.record("user-1")
    assert limiter.retry_after("user-1") > 0

    limiter.reset("user-1")
    assert limiter.retry_after("user-1") == 0


def test_old_attempts_outside_the_window_are_not_counted():
    """A slow trickle of failures must never accumulate into a lockout."""
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=3, window_seconds=60, clock=clock)

    for _ in range(5):
        limiter.record("user-1")
        clock.advance(30)

    # Only the last two land inside the 60s window.
    assert limiter.retry_after("user-1") == 0


def test_entries_are_evicted_so_the_map_cannot_grow_without_bound():
    """An attacker cycling keys must not be able to exhaust memory."""
    clock = FakeClock()
    limiter = RateLimiter(max_attempts=2, window_seconds=60, clock=clock)

    for i in range(500):
        limiter.record(f"key-{i}")

    clock.advance(61)
    limiter.record("fresh-key")

    assert len(limiter._attempts) < 500
