import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.core.http import RequestMetaDep
from app.core.rate_limit import AuthLimitsDep
from app.core.responses import Envelope, ok
from app.modules.auth.deps import CurrentPrincipal, require_permission
from app.modules.payments import schemas, service
from app.modules.payments.models import Payment, Refund
from app.modules.rbac.principal import Principal

router = APIRouter(prefix="/payments", tags=["payments"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100)]
MAX_WEBHOOK_BYTES = 64 * 1024


def _providers(request: Request) -> dict:  # type: ignore[type-arg]
    providers: dict = request.app.state.payment_providers  # type: ignore[type-arg]
    return providers


def _out(p: Payment) -> schemas.PaymentOut:
    return schemas.PaymentOut(
        id=p.id, purpose=p.purpose, status=p.status, method=p.method, provider=p.provider, amount_ugx=p.amount_ugx,
        currency=p.currency, checkout_url=p.checkout_url if p.status == "PENDING" else None,
        print_order_id=p.print_order_id, resource_id=p.resource_id, failure_reason=p.failure_reason,
        created_at=p.created_at, paid_at=p.paid_at,
    )  # fmt: skip


def _refund_out(r: Refund) -> schemas.RefundOut:
    return schemas.RefundOut(
        id=r.id, payment_id=r.payment_id, amount_ugx=r.amount_ugx, status=r.status, reason=r.reason
    )


@router.get(
    "/config",
    response_model=Envelope[schemas.PaymentConfigOut],
    summary="Is online payment available?",
)
def payment_config() -> Envelope[schemas.PaymentConfigOut]:
    s = get_settings()
    return ok(
        schemas.PaymentConfigOut(
            online_available=s.payments_available,
            provider=s.payment_provider if s.payments_available else None,
        )
    )


@router.post("", status_code=201, response_model=Envelope[schemas.PaymentOut])
def create_payment(
    body: schemas.PaymentCreate, request: Request, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("payment:create"))], idempotency_key: IdemKey = None,
) -> Envelope[schemas.PaymentOut]:  # fmt: skip
    payment = service.create_online_payment(
        db, principal, order_id=body.order_id, resource_id=body.resource_id, idempotency_key=idempotency_key,
        providers=_providers(request), settings=get_settings(), meta=meta,
    )  # fmt: skip
    return ok(_out(payment))


@router.get("/{payment_id}", response_model=Envelope[schemas.PaymentOut])
def get_payment(
    payment_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> Envelope[schemas.PaymentOut]:
    return ok(_out(service.get_payment(db, principal, payment_id)))


@router.post(
    "/{payment_id}/verify",
    response_model=Envelope[schemas.PaymentOut],
    summary="Re-check with the provider",
)
def verify_payment(
    payment_id: uuid.UUID, request: Request, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep, principal: CurrentPrincipal,
) -> Envelope[schemas.PaymentOut]:  # fmt: skip
    limits.check_key("pay-verify", str(principal.user.id))
    return ok(_out(service.verify_payment(db, principal, payment_id, _providers(request), meta)))


@router.post("/{payment_id}/refund", response_model=Envelope[schemas.RefundOut])
def refund_payment(
    payment_id: uuid.UUID, request: Request, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("payment:manage"))],
) -> Envelope[schemas.RefundOut]:  # fmt: skip
    return ok(
        _refund_out(service.process_refund(db, principal, payment_id, _providers(request), meta))
    )


@router.post(
    "/webhooks/{provider_name}",
    response_model=Envelope[schemas.WebhookAck],
    summary="Provider webhook (signature-verified)",
)
async def webhook(
    provider_name: str, request: Request, db: DbSession, meta: RequestMetaDep, limits: AuthLimitsDep
) -> Envelope[schemas.WebhookAck]:
    provider = _providers(request).get(provider_name)
    if provider is None:
        raise NotFoundError("Unknown provider.")
    limits.check_ip("webhook", meta.ip)
    body = await request.body()  # the RAW bytes: the signature covers exactly these
    if len(body) > MAX_WEBHOOK_BYTES:
        raise PayloadTooLargeError("Webhook body too large.")
    result = await run_in_threadpool(
        service.process_webhook, db, provider, dict(request.headers), body, meta
    )
    return ok(schemas.WebhookAck(status=result.status))


@router.post(
    "/dev/simulate",
    response_model=Envelope[schemas.WebhookAck],
    summary="DEVELOPMENT ONLY: simulate the fake provider",
)
def simulate(
    body: schemas.SimulateIn, request: Request, db: DbSession, meta: RequestMetaDep, principal: CurrentPrincipal,
) -> Envelope[schemas.WebhookAck]:  # fmt: skip
    result = service.simulate_provider_event(
        db, principal, body.payment_id, body.outcome, _providers(request), get_settings(), meta
    )
    return ok(schemas.WebhookAck(status=result.status))
