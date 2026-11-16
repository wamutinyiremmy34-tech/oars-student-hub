from types import SimpleNamespace

import pytest

from app.core.errors import RateLimitedError
from app.core.http import get_client_ip
from app.core.rate_limit import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_limit_and_reports_retry_after() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock=clock)
    for _ in range(3):
        limiter.hit("k", limit=3, window_seconds=60)
    with pytest.raises(RateLimitedError) as exc:
        limiter.hit("k", limit=3, window_seconds=60)
    assert exc.value.status_code == 429
    assert exc.value.headers is not None
    assert int(exc.value.headers["Retry-After"]) == 60


def test_limiter_window_slides_and_keys_are_independent() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock=clock)
    limiter.hit("a", limit=1, window_seconds=60)
    limiter.hit("b", limit=1, window_seconds=60)  # different key unaffected
    with pytest.raises(RateLimitedError):
        limiter.hit("a", limit=1, window_seconds=60)
    clock.now += 61
    limiter.hit("a", limit=1, window_seconds=60)  # window has slid past the first hit


def test_disabled_limiter_never_blocks() -> None:
    limiter = SlidingWindowRateLimiter(enabled=False)
    for _ in range(100):
        limiter.hit("k", limit=1, window_seconds=60)


def _request(forwarded: str | None, host: str = "10.0.0.9") -> SimpleNamespace:
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_forwarded_header_is_ignored_without_trusted_proxies() -> None:
    assert get_client_ip(_request("1.2.3.4"), 0) == "10.0.0.9"  # type: ignore[arg-type]


def test_forwarded_header_uses_nth_hop_from_the_right() -> None:
    # A client-supplied fake first hop must not be believed when one proxy is trusted.
    request = _request("6.6.6.6, 203.0.113.7")
    assert get_client_ip(request, 1) == "203.0.113.7"  # type: ignore[arg-type]
    assert get_client_ip(request, 2) == "6.6.6.6"  # type: ignore[arg-type]


def test_falls_back_to_socket_address() -> None:
    assert get_client_ip(_request(None), 1) == "10.0.0.9"  # type: ignore[arg-type]
