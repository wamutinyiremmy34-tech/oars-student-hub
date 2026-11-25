import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import PayloadTooLargeError
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.auth.deps import require_permission
from app.modules.auth.schemas import MessageOut
from app.modules.printing import operator, schemas, service, shops
from app.modules.rbac.principal import Principal
from app.modules.users.models import User
from app.providers.deps import ScannerDep, StorageDep

shops_router = APIRouter(prefix="/print/shops", tags=["printing"])
print_router = APIRouter(prefix="/print", tags=["printing"])
operator_router = APIRouter(prefix="/operator", tags=["operator"])

Page = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=50)]
StatusFilter = Annotated[str | None, Query(pattern="^[A-Z_]{4,20}$")]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100)]
Customer = Annotated[Principal, Depends(require_permission("order:create"))]
ShopAdmin = Annotated[Principal, Depends(require_permission("printshop:manage"))]
Reader = Annotated[Principal, Depends(require_permission("order:read_any"))]
Writer = Annotated[Principal, Depends(require_permission("order:update_status"))]


def _meta(page: int, size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": size, "total": total}


def _shop_out(s) -> schemas.ShopOut:  # type: ignore[no-untyped-def]
    return schemas.ShopOut(
        id=s.id,
        institution_id=s.institution_id,
        name=s.name,
        location=s.location,
        is_active=s.is_active,
        pay_on_pickup_enabled=s.pay_on_pickup_enabled,
    )


def _rule_out(r) -> schemas.RuleOut:  # type: ignore[no-untyped-def]
    return schemas.RuleOut(
        id=r.id,
        kind=r.kind,
        paper_size=r.paper_size,
        color_mode=r.color_mode,
        duplex=r.duplex,
        option_key=r.option_key,
        amount_ugx=r.amount_ugx,
        is_active=r.is_active,
    )


# ------------------------------------------------------------------ shops (public reads, admin writes)
@shops_router.get("", response_model=Envelope[list[schemas.ShopOut]])
def list_shops(
    db: DbSession,
    institution_id: uuid.UUID,
    include_inactive: bool = False,
    principal: ShopAdmin | None = None,
) -> Envelope[list[schemas.ShopOut]]:
    # Admins can request all shops; everyone else gets only active ones
    if include_inactive and principal is not None:
        return ok([_shop_out(s) for s in shops.list_shops_all(db, institution_id)])
    return ok([_shop_out(s) for s in shops.list_shops(db, institution_id)])


@shops_router.get(
    "/{shop_id}/pricing",
    response_model=Envelope[list[schemas.RuleOut]],
    summary="Public price list",
)
def pricing(shop_id: uuid.UUID, db: DbSession) -> Envelope[list[schemas.RuleOut]]:
    shops.get_shop(db, shop_id)
    return ok([_rule_out(r) for r in shops.active_rules(db, shop_id)])


@shops_router.post("", status_code=201, response_model=Envelope[schemas.ShopOut])
def create_shop(
    body: schemas.ShopIn, db: DbSession, meta: RequestMetaDep, principal: ShopAdmin
) -> Envelope[schemas.ShopOut]:
    return ok(_shop_out(shops.create_shop(db, principal, body, meta)))


@shops_router.patch("/{shop_id}", response_model=Envelope[schemas.ShopOut])
def update_shop(
    shop_id: uuid.UUID,
    body: schemas.ShopPatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: ShopAdmin,
) -> Envelope[schemas.ShopOut]:
    return ok(_shop_out(shops.update_shop(db, principal, shop_id, body, meta)))


@shops_router.post("/{shop_id}/staff", status_code=201, response_model=Envelope[MessageOut])
def add_staff(
    shop_id: uuid.UUID,
    body: schemas.StaffIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: ShopAdmin,
) -> Envelope[MessageOut]:
    shops.add_staff(db, principal, shop_id, body.user_id, meta)
    return ok(MessageOut(message="Added to the shop's staff."))


@shops_router.delete("/{shop_id}/staff/{user_id}", response_model=Envelope[MessageOut])
def remove_staff(
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    meta: RequestMetaDep,
    principal: ShopAdmin,
) -> Envelope[MessageOut]:
    shops.remove_staff(db, principal, shop_id, user_id, meta)
    return ok(MessageOut(message="Removed from the shop's staff."))


@shops_router.post(
    "/{shop_id}/pricing-rules", status_code=201, response_model=Envelope[schemas.RuleOut]
)
def add_rule(
    shop_id: uuid.UUID,
    body: schemas.RuleIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: ShopAdmin,
) -> Envelope[schemas.RuleOut]:
    return ok(_rule_out(shops.add_rule(db, principal, shop_id, body, meta)))


@shops_router.patch("/{shop_id}/pricing-rules/{rule_id}", response_model=Envelope[schemas.RuleOut])
def update_rule(
    shop_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.RulePatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: ShopAdmin,
) -> Envelope[schemas.RuleOut]:
    return ok(_rule_out(shops.update_rule(db, principal, shop_id, rule_id, body, meta)))


# ------------------------------------------------------------------ student
def _upload_limit(request: Request) -> None:
    declared = request.headers.get("content-length")
    if (
        declared
        and declared.isdigit()
        and int(declared) > get_settings().max_upload_bytes + 1024 * 1024
    ):
        raise PayloadTooLargeError("The uploaded file is too large.", code="file_too_large")


@print_router.post(
    "/documents",
    status_code=201,
    response_model=Envelope[schemas.DocumentOut],
    dependencies=[Depends(_upload_limit)],
)
def upload_document(
    file: Annotated[UploadFile, File()], db: DbSession, storage: StorageDep, scanner: ScannerDep,
    meta: RequestMetaDep, principal: Customer,
) -> Envelope[schemas.DocumentOut]:  # fmt: skip
    document, stored = service.upload_document(
        db, principal, file, storage=storage, scanner=scanner, settings=get_settings(), meta=meta
    )
    return ok(
        schemas.DocumentOut(
            id=document.id,
            filename=stored.original_filename,
            page_count=document.page_count,
            size_bytes=stored.size_bytes,
        )
    )


@print_router.post("/quote", response_model=Envelope[schemas.QuoteOut])
def quote(body: schemas.QuoteIn, db: DbSession, principal: Customer) -> Envelope[schemas.QuoteOut]:
    return ok(service.quote(db, principal, body))


@print_router.post("/orders", status_code=201, response_model=Envelope[schemas.OrderOut])
def create_order(
    body: schemas.OrderCreate, response: Response, db: DbSession, meta: RequestMetaDep,
    principal: Customer, idempotency_key: IdemKey = None,
) -> Envelope[schemas.OrderOut]:  # fmt: skip
    settings = get_settings()
    order, created = service.create_order(db, principal, body, idempotency_key, settings, meta)
    if not created:
        response.status_code = (
            200  # a replay of the same Idempotency-Key returns the original order
        )
    return ok(service.order_out(db, order, settings, as_owner=True))


@print_router.get("/orders", response_model=Envelope[list[schemas.OrderSummary]])
def list_orders(
    db: DbSession, principal: Annotated[Principal, Depends(require_permission("order:read"))],
    status: StatusFilter = None, page: Page = 1, page_size: PageSize = 10,
) -> Envelope[list[schemas.OrderSummary]]:  # fmt: skip
    rows, total = service.list_orders(db, principal, status, page, page_size)
    return ok(service.summaries(db, rows), meta=_meta(page, page_size, total))


@print_router.get("/orders/{order_id}", response_model=Envelope[schemas.OrderOut])
def get_order(
    order_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("order:read"))],
) -> Envelope[schemas.OrderOut]:
    order = service.own_order(db, principal, order_id)
    return ok(service.order_out(db, order, get_settings(), as_owner=True))


@print_router.post("/orders/{order_id}/submit", response_model=Envelope[schemas.OrderOut])
def submit_order(
    order_id: uuid.UUID, db: DbSession, meta: RequestMetaDep, principal: Customer
) -> Envelope[schemas.OrderOut]:
    settings = get_settings()
    return ok(
        service.order_out(
            db,
            service.submit_draft(db, principal, order_id, settings, meta),
            settings,
            as_owner=True,
        )
    )


@print_router.post("/orders/{order_id}/cancel", response_model=Envelope[schemas.OrderOut])
def cancel_order(
    order_id: uuid.UUID,
    body: schemas.CancelIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Customer,
) -> Envelope[schemas.OrderOut]:
    order = service.cancel_order(db, principal, order_id, body.reason, meta)
    return ok(service.order_out(db, order, get_settings(), as_owner=True))


# ------------------------------------------------------------------ operator
@operator_router.get("/shops", response_model=Envelope[list[schemas.ShopOut]])
def my_shops(db: DbSession, principal: Reader) -> Envelope[list[schemas.ShopOut]]:
    return ok([_shop_out(s) for s in operator.accessible_shops(db, principal)])


@operator_router.get("/orders", response_model=Envelope[list[schemas.OrderSummary]])
def queue(
    db: DbSession, principal: Reader, shop_id: uuid.UUID | None = None,
    status: StatusFilter = None, page: Page = 1, page_size: PageSize = 20,
) -> Envelope[list[schemas.OrderSummary]]:  # fmt: skip
    rows, total = operator.queue(db, principal, shop_id, status, page, page_size)
    return ok(service.summaries(db, rows, with_student=True), meta=_meta(page, page_size, total))


@operator_router.get("/orders/{order_id}", response_model=Envelope[schemas.OrderOut])
def order_detail(
    order_id: uuid.UUID, db: DbSession, principal: Reader
) -> Envelope[schemas.OrderOut]:
    return ok(operator.detail(db, principal, order_id, get_settings()))


def _op(db, order):  # type: ignore[no-untyped-def]
    student = db.get(User, order.student_id)
    return ok(
        service.order_out(
            db,
            order,
            get_settings(),
            as_owner=False,
            student_name=student.full_name if student else None,
        )
    )


@operator_router.post("/orders/{order_id}/accept", response_model=Envelope[schemas.OrderOut])
def accept(
    order_id: uuid.UUID, db: DbSession, meta: RequestMetaDep, principal: Writer
) -> Envelope[schemas.OrderOut]:
    return _op(db, operator.accept(db, principal, order_id, meta))


@operator_router.post("/orders/{order_id}/reject", response_model=Envelope[schemas.OrderOut])
def reject(
    order_id: uuid.UUID,
    body: schemas.RejectIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Writer,
) -> Envelope[schemas.OrderOut]:
    return _op(db, operator.reject(db, principal, order_id, body.reason, meta))


@operator_router.post("/orders/{order_id}/printing", response_model=Envelope[schemas.OrderOut])
def start_printing(
    order_id: uuid.UUID, db: DbSession, meta: RequestMetaDep, principal: Writer
) -> Envelope[schemas.OrderOut]:
    return _op(db, operator.start_printing(db, principal, order_id, meta))


@operator_router.post("/orders/{order_id}/ready", response_model=Envelope[schemas.OrderOut])
def ready(
    order_id: uuid.UUID, db: DbSession, meta: RequestMetaDep, principal: Writer
) -> Envelope[schemas.OrderOut]:
    return _op(db, operator.mark_ready(db, principal, order_id, meta))


@operator_router.post(
    "/orders/{order_id}/payment",
    response_model=Envelope[schemas.OrderOut],
    summary="Record pay-on-pickup cash",
)
def record_cash(
    order_id: uuid.UUID,
    body: schemas.CashIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Writer,
) -> Envelope[schemas.OrderOut]:
    return _op(db, operator.record_cash(db, principal, order_id, body.amount_ugx, meta))


@operator_router.post("/orders/{order_id}/complete", response_model=Envelope[schemas.OrderOut])
def complete(
    order_id: uuid.UUID,
    body: schemas.CompleteIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Writer,
) -> Envelope[schemas.OrderOut]:
    return _op(
        db, operator.complete(db, principal, order_id, body.pickup_code, get_settings(), meta)
    )


@operator_router.post(
    "/orders/{order_id}/items/{item_id}/document-link", response_model=Envelope[schemas.LinkOut]
)
def document_link(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    storage: StorageDep,
    meta: RequestMetaDep,
    principal: Reader,
) -> Envelope[schemas.LinkOut]:
    return ok(operator.document_link(db, principal, order_id, item_id, storage, meta))


@operator_router.post("/orders/{order_id}/hold", response_model=Envelope[MessageOut])
def retention_hold(
    order_id: uuid.UUID, body: schemas.HoldIn, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("order:manage_any"))],
) -> Envelope[MessageOut]:  # fmt: skip
    operator.set_hold(db, principal, order_id, body.hold, body.reason, meta)
    return ok(MessageOut(message="Retention hold set." if body.hold else "Retention hold cleared."))
