import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, model_validator


class PaymentCreate(BaseModel):
    """Exactly one target. The amount is NEVER accepted from the client: the server reads it from the order or resource."""

    order_id: uuid.UUID | None = None
    resource_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if (self.order_id is None) == (self.resource_id is None):
            raise ValueError("provide exactly one of order_id or resource_id")
        return self


class PaymentOut(BaseModel):
    id: uuid.UUID
    purpose: str
    status: str
    method: str
    provider: str
    amount_ugx: int
    currency: str
    checkout_url: str | None
    print_order_id: uuid.UUID | None
    resource_id: uuid.UUID | None
    failure_reason: str | None
    created_at: datetime
    paid_at: datetime | None


class PaymentConfigOut(BaseModel):
    online_available: bool
    provider: str | None


class SimulateIn(BaseModel):
    payment_id: uuid.UUID
    outcome: Literal["success", "failure"]


class WebhookAck(BaseModel):
    status: str


class RefundOut(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount_ugx: int
    status: str
    reason: str
