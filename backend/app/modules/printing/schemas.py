import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

PaperSize = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{2,10}$")
]
ColorMode = Literal["BW", "COLOR"]
PaymentMethod = Literal["ONLINE", "PAY_ON_PICKUP"]
_OPTION_KEY = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


class ItemIn(BaseModel):
    document_id: uuid.UUID
    copies: int = Field(default=1, ge=1, le=100)
    paper_size: PaperSize = "A4"
    color_mode: ColorMode = "BW"
    duplex: bool = False
    options: dict[str, bool] = Field(
        default_factory=dict, description="Extra options, e.g. {'staple': true}"
    )

    @field_validator("options")
    @classmethod
    def _option_keys(cls, value: dict[str, bool]) -> dict[str, bool]:
        if len(value) > 10 or any(not _OPTION_KEY.match(k) for k in value):
            raise ValueError("invalid options")
        return value


class QuoteIn(BaseModel):
    shop_id: uuid.UUID
    items: list[ItemIn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _unique_documents(self) -> Self:
        ids = [i.document_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each document can appear once")
        return self


class OrderCreate(QuoteIn):
    payment_method: PaymentMethod
    # A guard against stale quotes ONLY. The server always calculates the price itself and
    # refuses (409 price_changed) if this differs; it is never used as the price.
    expected_total_ugx: int | None = Field(default=None, ge=1)
    draft: bool = False
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class CancelIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class RejectIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class CompleteIn(BaseModel):
    pickup_code: Annotated[
        str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=4, max_length=12)
    ]


class CashIn(BaseModel):
    amount_ugx: int = Field(ge=1, description="The cash received; must equal the order total")


class HoldIn(BaseModel):
    hold: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None


# ---- shops and pricing
class ShopIn(BaseModel):
    institution_id: uuid.UUID
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    location: Annotated[str, StringConstraints(max_length=255)] | None = None
    pay_on_pickup_enabled: bool = True
    max_outstanding_pickup_orders: int | None = Field(default=None, ge=0, le=50)


class ShopPatch(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
        | None
    ) = None
    location: Annotated[str, StringConstraints(max_length=255)] | None = None
    is_active: bool | None = None
    pay_on_pickup_enabled: bool | None = None
    max_outstanding_pickup_orders: int | None = Field(default=None, ge=0, le=50)


class ShopOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    name: str
    location: str | None
    is_active: bool
    pay_on_pickup_enabled: bool


class StaffIn(BaseModel):
    user_id: uuid.UUID


class RuleIn(BaseModel):
    kind: Literal["PER_PAGE", "PER_COPY", "PER_ORDER"]
    paper_size: PaperSize | None = None
    color_mode: ColorMode | None = None
    duplex: bool | None = None
    option_key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,29}$")] | None = None
    amount_ugx: int = Field(ge=0, le=10_000_000)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.kind == "PER_PAGE":
            if not (self.paper_size and self.color_mode) or self.option_key or self.amount_ugx < 1:
                raise ValueError(
                    "PER_PAGE needs paper_size, color_mode and a positive amount, and no option_key"
                )
        elif not self.option_key:
            raise ValueError(f"{self.kind} needs an option_key")
        return self


class RulePatch(BaseModel):
    amount_ugx: int | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    kind: str
    paper_size: str | None
    color_mode: str | None
    duplex: bool | None
    option_key: str | None
    amount_ugx: int
    is_active: bool


# ---- documents, quotes, orders
class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    page_count: int
    size_bytes: int


class QuoteItemOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    page_count: int
    copies: int
    paper_size: str
    color_mode: str
    duplex: bool
    options: dict[str, bool]
    unit_price_ugx: int
    line_total_ugx: int
    lines: list[dict[str, Any]]


class QuoteOut(BaseModel):
    shop_id: uuid.UUID
    currency: str
    total_ugx: int
    items: list[QuoteItemOut]
    order_lines: list[dict[str, Any]]


class OrderItemOut(BaseModel):
    id: uuid.UUID
    position: int
    filename: str
    page_count: int
    copies: int
    paper_size: str
    color_mode: str
    duplex: bool
    options: dict[str, Any]
    unit_price_ugx: int
    line_total_ugx: int
    document_available: bool


class HistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class PaymentSummary(BaseModel):
    id: uuid.UUID
    status: str
    method: str
    amount_ugx: int
    checkout_url: str | None  # only while PENDING, so the student can resume
    created_at: datetime
    paid_at: datetime | None


class OrderSummary(BaseModel):
    id: uuid.UUID
    status: str
    payment_method: str
    payment_status: str
    total_ugx: int
    shop_name: str
    item_count: int
    created_at: datetime
    student_name: str | None = None


class OrderOut(BaseModel):
    id: uuid.UUID
    status: str
    payment_method: str
    payment_status: str
    total_ugx: int
    currency: str = "UGX"
    shop: ShopOut
    items: list[OrderItemOut]
    history: list[HistoryOut]
    payment: PaymentSummary | None
    note: str | None
    reject_reason: str | None
    cancel_reason: str | None
    pickup_code: str | None  # only ever shown to the student who owns the order
    can_cancel: bool
    awaiting_payment: bool
    created_at: datetime
    # operator view only
    student_name: str | None = None
    retention_hold: bool | None = None


class LinkOut(BaseModel):
    url: str
    expires_in: int
    filename: str
