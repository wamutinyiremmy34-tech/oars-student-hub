"""Audit trail. record() only adds the row; the caller commits it in the same transaction as the change.

Security events that precede an error response (e.g. failed login) must be committed explicitly
before raising, otherwise the request's rollback would discard them.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.http import RequestMeta
from app.core.logging import SENSITIVE_KEY_FRAGMENTS
from app.modules.audit.models import AuditLog


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def scrub(value: Any) -> Any:
    """Defence in depth: redact any key that looks like a password, secret, token or cookie."""
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _is_sensitive(str(k)) else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def record(
    db: Session,
    *,
    action: str,
    outcome: str = "SUCCESS",
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    institution_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    meta: RequestMeta | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=target_id,
        institution_id=institution_id,
        details=scrub(details) if details else None,
        ip_address=meta.ip if meta else None,
        user_agent=meta.user_agent if meta else None,
        request_id=meta.request_id if meta else None,
    )
    db.add(entry)
    return entry
