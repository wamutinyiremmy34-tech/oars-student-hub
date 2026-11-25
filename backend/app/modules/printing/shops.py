"""Print shops, their staff and pricing rules (administration)."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.http import RequestMeta
from app.modules.audit import service as audit
from app.modules.institutions.models import Institution
from app.modules.printing import schemas
from app.modules.printing.models import PrintPricingRule, PrintShop, PrintShopStaff
from app.modules.rbac.principal import Principal
from app.modules.users.models import User

MANAGE = "printshop:manage"


def list_shops(db: Session, institution_id: uuid.UUID) -> list[PrintShop]:
    stmt = select(PrintShop).where(
        PrintShop.institution_id == institution_id, PrintShop.is_active.is_(True)
    )
    return list(db.scalars(stmt.order_by(PrintShop.name)))


def list_shops_all(db: Session, institution_id: uuid.UUID) -> list[PrintShop]:
    """Return all shops for an institution regardless of is_active (admin use)."""
    stmt = select(PrintShop).where(PrintShop.institution_id == institution_id)
    return list(db.scalars(stmt.order_by(PrintShop.name)))


def get_shop(db: Session, shop_id: uuid.UUID) -> PrintShop:
    shop = db.get(PrintShop, shop_id)
    if shop is None:
        raise NotFoundError("Print shop not found.")
    return shop


def active_rules(db: Session, shop_id: uuid.UUID) -> list[PrintPricingRule]:
    stmt = select(PrintPricingRule).where(
        PrintPricingRule.shop_id == shop_id, PrintPricingRule.is_active.is_(True)
    )
    return list(
        db.scalars(
            stmt.order_by(PrintPricingRule.kind, PrintPricingRule.paper_size, PrintPricingRule.id)
        )
    )


def _manageable(db: Session, principal: Principal, shop_id: uuid.UUID) -> PrintShop:
    shop = db.get(PrintShop, shop_id)
    if shop is None or not principal.can(MANAGE, shop.institution_id):
        raise NotFoundError("Print shop not found.")  # outside your institution it does not exist
    return shop


def _commit(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"That {what} already exists.", code="already_exists") from exc


def create_shop(
    db: Session, principal: Principal, data: schemas.ShopIn, meta: RequestMeta
) -> PrintShop:
    principal.require(MANAGE, data.institution_id)
    if db.get(Institution, data.institution_id) is None:
        raise NotFoundError("Institution not found.")
    shop = PrintShop(**data.model_dump())
    db.add(shop)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That print shop already exists.", code="already_exists") from exc
    audit.record(db, action="printshop.created", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, meta=meta)  # fmt: skip
    _commit(db, "print shop")
    return shop


def update_shop(
    db: Session,
    principal: Principal,
    shop_id: uuid.UUID,
    patch: schemas.ShopPatch,
    meta: RequestMeta,
) -> PrintShop:
    shop = _manageable(db, principal, shop_id)
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(shop, field, value)
    audit.record(db, action="printshop.updated", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, meta=meta)  # fmt: skip
    _commit(db, "print shop")
    return shop


def add_staff(
    db: Session, principal: Principal, shop_id: uuid.UUID, user_id: uuid.UUID, meta: RequestMeta
) -> None:
    shop = _manageable(db, principal, shop_id)
    if db.get(User, user_id) is None:
        raise NotFoundError("User not found.")
    if db.get(PrintShopStaff, (shop.id, user_id)) is not None:
        raise ConflictError("Already on this shop's staff.", code="already_exists")
    db.add(PrintShopStaff(shop_id=shop.id, user_id=user_id, added_by_user_id=principal.user.id))
    audit.record(db, action="printshop.staff_added", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, details={"user_id": str(user_id)}, meta=meta)  # fmt: skip
    db.commit()


def remove_staff(
    db: Session, principal: Principal, shop_id: uuid.UUID, user_id: uuid.UUID, meta: RequestMeta
) -> None:
    shop = _manageable(db, principal, shop_id)
    member = db.get(PrintShopStaff, (shop.id, user_id))
    if member is None:
        raise NotFoundError("Not on this shop's staff.")
    db.delete(member)
    audit.record(db, action="printshop.staff_removed", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, details={"user_id": str(user_id)}, meta=meta)  # fmt: skip
    db.commit()


def add_rule(
    db: Session, principal: Principal, shop_id: uuid.UUID, data: schemas.RuleIn, meta: RequestMeta
) -> PrintPricingRule:
    shop = _manageable(db, principal, shop_id)
    # Two live rules for the same combination would make the price ambiguous.
    for existing in active_rules(db, shop.id):
        same = (existing.kind, existing.paper_size, existing.color_mode, existing.duplex, existing.option_key) == (
            data.kind, data.paper_size, data.color_mode, data.duplex, data.option_key
        )  # fmt: skip
        if same:
            raise ConflictError(
                "An active rule for that combination already exists. Deactivate it first.",
                code="already_exists",
            )
    rule = PrintPricingRule(shop_id=shop.id, **data.model_dump())
    db.add(rule)
    db.flush()
    audit.record(db, action="printshop.pricing_rule_added", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, details={"rule_id": str(rule.id), "amount_ugx": data.amount_ugx}, meta=meta)  # fmt: skip
    db.commit()
    return rule


def update_rule(
    db: Session,
    principal: Principal,
    shop_id: uuid.UUID,
    rule_id: uuid.UUID,
    patch: schemas.RulePatch,
    meta: RequestMeta,
) -> PrintPricingRule:
    shop = _manageable(db, principal, shop_id)
    rule = db.get(PrintPricingRule, rule_id)
    if rule is None or rule.shop_id != shop.id:
        raise NotFoundError("Pricing rule not found.")
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(
            rule, field, value
        )  # past orders are unaffected: they carry their own price snapshot
    audit.record(db, action="printshop.pricing_rule_updated", actor_user_id=principal.user.id, target_type="print_shop",
                 target_id=str(shop.id), institution_id=shop.institution_id, details={"rule_id": str(rule.id)}, meta=meta)  # fmt: skip
    db.commit()
    return rule
