import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.modules.rbac.principal import Principal
from app.modules.rbac.service import load_grants
from app.modules.users.models import User, UserStatus

_bearer = HTTPBearer(auto_error=False)
_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def get_current_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Authenticate the request. The user and grants are re-read from the database on every request,
    so suspension and role changes take effect immediately, not when the access token expires."""
    if credentials is None:
        raise UnauthorizedError(headers=_CHALLENGE)
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise UnauthorizedError("Invalid or expired token.", code="invalid_token") from exc
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError(
            "Invalid or expired token.", code="invalid_token", headers=_CHALLENGE
        )
    return Principal(user=user, grants=load_grants(db, user.id))


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_optional_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal | None:
    """Public endpoints that personalise for signed-in users. A bad token is still a 401 (never silently anonymous)."""
    if credentials is None:
        return None
    return get_current_principal(db, credentials)


OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]


def require_permission(*permissions: str) -> Callable[[Principal], Principal]:
    """Coarse route-level gate: the caller must hold each permission in SOME scope.

    The handler/service must still apply the institution scope and ownership rules to the specific
    object (see Principal.can / authorize_over_user). Route-level checks alone are not sufficient.
    """

    def dependency(principal: CurrentPrincipal) -> Principal:
        for permission in permissions:
            if not principal.has_any_scope(permission):
                raise ForbiddenError()
        return principal

    return dependency


def require_trusted_origin(request: Request) -> None:
    """CSRF defence-in-depth for cookie-authenticated endpoints (refresh, logout).

    Browsers always send Origin on cross-site POSTs, so a present-but-unlisted Origin is rejected.
    Non-browser clients (no Origin) cannot be driven by a victim's cookies, so they are allowed.
    SameSite=Lax on the cookie is the primary defence.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin.rstrip("/") not in get_settings().cors_origins:
        raise ForbiddenError("Request origin is not allowed.", code="origin_not_allowed")
