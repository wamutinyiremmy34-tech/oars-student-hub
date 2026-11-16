"""Request metadata used for audit logs and rate limiting."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import get_settings


@dataclass(frozen=True)
class RequestMeta:
    ip: str
    user_agent: str | None
    request_id: str | None


def get_client_ip(request: Request, trusted_proxy_count: int) -> str:
    """Client IP. X-Forwarded-For is only honoured when a known number of proxies sit in front of us.

    With N trusted proxies each appending one hop, the real client address is the Nth from the right.
    Taking the left-most value would let any client spoof its IP and dodge rate limits.
    """
    if trusted_proxy_count > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if len(hops) >= trusted_proxy_count:
                return hops[-trusted_proxy_count]
    return request.client.host if request.client else "unknown"


def get_request_meta(request: Request) -> RequestMeta:
    settings = get_settings()
    user_agent = request.headers.get("user-agent")
    return RequestMeta(
        ip=get_client_ip(request, settings.trusted_proxy_count),
        user_agent=user_agent[:255] if user_agent else None,
        request_id=getattr(request.state, "request_id", None),
    )


RequestMetaDep = Annotated[RequestMeta, Depends(get_request_meta)]
