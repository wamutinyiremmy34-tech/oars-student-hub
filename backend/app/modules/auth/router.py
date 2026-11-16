from fastapi import APIRouter, Depends, Request, Response

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import UnauthorizedError
from app.core.http import RequestMetaDep
from app.core.rate_limit import AuthLimitsDep
from app.core.responses import Envelope, ok
from app.modules.auth import service
from app.modules.auth.cookies import clear_refresh_cookie, set_refresh_cookie
from app.modules.auth.deps import require_trusted_origin
from app.modules.auth.schemas import (
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    RegisterOut,
    ResetPasswordIn,
    TokenOut,
    VerifyIn,
)
from app.modules.users.schemas import UserPublic
from app.providers.email import EmailSenderDep

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_out(issued: service.IssuedSession) -> TokenOut:
    return TokenOut(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post("/register", status_code=201, response_model=Envelope[RegisterOut])
def register(
    body: RegisterIn,
    db: DbSession,
    meta: RequestMetaDep,
    limits: AuthLimitsDep,
    email_sender: EmailSenderDep,
) -> Envelope[RegisterOut]:
    limits.check_ip("register", meta.ip)
    user = service.register_student(db, body, meta=meta, email_sender=email_sender)
    return ok(RegisterOut(user=UserPublic.from_user(user)))


@router.post("/login", response_model=Envelope[TokenOut])
def login(
    body: LoginIn, response: Response, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep
) -> Envelope[TokenOut]:
    limits.check_ip("login", meta.ip)
    limits.check_key("login", service.normalize_email(body.email))
    issued = service.login(db, email=body.email, password=body.password, meta=meta)
    set_refresh_cookie(response, issued.refresh_token)
    return ok(_token_out(issued))


@router.post(
    "/refresh",
    response_model=Envelope[TokenOut],
    dependencies=[Depends(require_trusted_origin)],
)
def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    meta: RequestMetaDep,
    limits: AuthLimitsDep,
) -> Envelope[TokenOut]:
    limits.check_ip("refresh", meta.ip)
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if not raw:
        raise UnauthorizedError("Your session has expired.", code="invalid_refresh_token")
    issued = service.refresh_session(db, raw_token=raw, meta=meta)
    set_refresh_cookie(response, issued.refresh_token)
    return ok(_token_out(issued))


@router.post(
    "/logout",
    response_model=Envelope[MessageOut],
    dependencies=[Depends(require_trusted_origin)],
)
def logout(
    request: Request, response: Response, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep
) -> Envelope[MessageOut]:
    limits.check_ip("logout", meta.ip)
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if raw:
        service.logout(db, raw_token=raw, meta=meta)
    clear_refresh_cookie(response)
    return ok(MessageOut(message="Signed out."))


@router.post("/verify", response_model=Envelope[MessageOut])
def verify(
    body: VerifyIn, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep
) -> Envelope[MessageOut]:
    limits.check_ip("verify", meta.ip)
    service.verify_email(db, raw_token=body.token, meta=meta)
    return ok(MessageOut(message="Email verified."))


@router.post("/forgot-password", response_model=Envelope[MessageOut])
def forgot_password(
    body: ForgotPasswordIn,
    db: DbSession,
    meta: RequestMetaDep,
    limits: AuthLimitsDep,
    email_sender: EmailSenderDep,
) -> Envelope[MessageOut]:
    limits.check_ip("forgot", meta.ip)
    limits.check_key("forgot", service.normalize_email(body.email))
    service.request_password_reset(db, email=body.email, meta=meta, email_sender=email_sender)
    # Identical response whether or not the account exists (no user enumeration).
    return ok(
        MessageOut(message="If an account exists for that email, a reset link has been sent.")
    )


@router.post("/reset-password", response_model=Envelope[MessageOut])
def reset_password(
    body: ResetPasswordIn, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep
) -> Envelope[MessageOut]:
    limits.check_ip("reset", meta.ip)
    service.reset_password(db, raw_token=body.token, new_password=body.new_password, meta=meta)
    return ok(MessageOut(message="Password updated. Please sign in."))
