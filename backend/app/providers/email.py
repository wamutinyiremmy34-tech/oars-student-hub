"""Email delivery abstraction. Real providers (SMTP, SES, ...) are added in a later phase.

Development/testing: messages are logged to the console.
Production: delivery is DISABLED until a real provider is implemented. Nothing is sent and message
contents (which carry one-time tokens) are never logged.
"""

import logging
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Request

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Development only: prints the email so you can click the verification/reset link."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email_console_delivery to=%s subject=%s\n%s", message.to, message.subject, message.body
        )


class DisabledEmailSender:
    def send(self, message: EmailMessage) -> None:
        logger.warning("email_delivery_disabled", extra={"subject": message.subject})


def build_email_sender(settings: Settings) -> EmailSender:
    return DisabledEmailSender() if settings.is_production else ConsoleEmailSender()


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
