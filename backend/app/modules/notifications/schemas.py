"""Notification API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    action_url: str | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountOut(BaseModel):
    count: int


class MarkReadIn(BaseModel):
    ids: list[uuid.UUID] = Field(
        default_factory=list, description="IDs to mark as read. Empty = mark all."
    )
