"""In-process sliding-window rate limiting.

Limitation: state is per API instance. Before running more than one instance, move this behind the
same interface using Redis (or another shared store).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import RateLimitedError

_MAX_TRACKED_KEYS = 10_000
_PRUNE_AFTER_SECONDS = 3600.0

# Many students share one campus NAT address, so per-IP limits are deliberately looser than the
# per-account limits.
IP_LIMIT_MULTIPLIER = 5


class SlidingWindowRateLimiter:
    def __init__(
        self, *, enabled: bool = True, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._enabled = enabled
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Record one attempt for `key`; raise RateLimitedError when the window is full."""
        if not self._enabled:
            return
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, math.ceil(hits[0] + window_seconds - now))
                raise RateLimitedError(headers={"Retry-After": str(retry_after)})
            hits.append(now)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._prune(now)

    def _prune(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or v[-1] <= now - _PRUNE_AFTER_SECONDS]
        for key in stale:
            del self._hits[key]


class AuthRateLimits:
    """Rate limits for authentication endpoints, configured from settings."""

    def __init__(self, limiter: SlidingWindowRateLimiter, settings: Settings) -> None:
        self._limiter = limiter
        self._limit = settings.auth_rate_limit_attempts
        self._window = settings.auth_rate_limit_window_seconds

    def check_ip(self, scope: str, ip: str) -> None:
        self._limiter.hit(
            f"{scope}:ip:{ip}",
            limit=self._limit * IP_LIMIT_MULTIPLIER,
            window_seconds=self._window,
        )

    def check_key(self, scope: str, key: str) -> None:
        self._limiter.hit(f"{scope}:key:{key}", limit=self._limit, window_seconds=self._window)


def get_auth_limits(request: Request) -> AuthRateLimits:
    return AuthRateLimits(request.app.state.rate_limiter, get_settings())


AuthLimitsDep = Annotated[AuthRateLimits, Depends(get_auth_limits)]
