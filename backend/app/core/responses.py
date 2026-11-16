"""API response envelopes. Success: {data, meta}. Error: {error: {...}}."""

from typing import Any

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def ok[T](data: T, meta: dict[str, Any] | None = None) -> Envelope[T]:
    return Envelope(data=data, meta=meta or {})
