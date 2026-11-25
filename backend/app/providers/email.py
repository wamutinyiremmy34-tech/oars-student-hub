"""Email delivery abstraction.

Priority order:
  1. SMTP — if SMTP_HOST is set, real emails are sent via smtplib (STARTTLS or SSL).
  2. Console — in development (APP_ENV != production) with no SMTP configured, messages are
     printed to stdout so the developer can click the verification / reset link immediately.
  3. Disabled — in production with no SMTP configured, messages are silently dropped
     (a warning is logged). Configure SMTP_HOST to enable real delivery in production.
"""

import email.utils
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.text import MIMEText
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


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class SmtpEmailSender:
    """Sends real email via SMTP.  Supports STARTTLS (port 587) and SSL (port 465)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        use_ssl: bool,
        from_address: str,
        from_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl
        self._from_address = from_address
        self._from_name = from_name

    def send(self, message: EmailMessage) -> None:
        mime = MIMEText(message.body, "plain", "utf-8")
        mime["Subject"] = message.subject
        mime["From"] = email.utils.formataddr((self._from_name, self._from_address))
        mime["To"] = message.to

        context = ssl.create_default_context()
        try:
            if self._use_ssl:
                with smtplib.SMTP_SSL(self._host, self._port, context=context) as smtp:
                    if self._username and self._password:
                        smtp.login(self._username, self._password)
                    smtp.sendmail(self._from_address, message.to, mime.as_string())
            else:
                with smtplib.SMTP(self._host, self._port) as smtp:
                    smtp.ehlo()
                    if self._use_tls:
                        smtp.starttls(context=context)
                        smtp.ehlo()
                    if self._username and self._password:
                        smtp.login(self._username, self._password)
                    smtp.sendmail(self._from_address, message.to, mime.as_string())
            logger.info("email_sent to=%s subject=%r", message.to, message.subject)
        except Exception:
            logger.exception(
                "email_send_failed to=%s subject=%r", message.to, message.subject
            )
            raise


class ConsoleEmailSender:
    """Development fallback: prints the full email body to stdout so you can click the link."""

    def send(self, message: EmailMessage) -> None:
        separator = "─" * 60
        print(
            f"\n{separator}\n"
            f"📧  DEV EMAIL (not sent — no SMTP configured)\n"
            f"To:      {message.to}\n"
            f"Subject: {message.subject}\n"
            f"{separator}\n"
            f"{message.body}\n"
            f"{separator}\n",
            flush=True,
        )
        logger.info("email_console_delivery to=%s subject=%s", message.to, message.subject)


class DisabledEmailSender:
    """Production fallback when SMTP is not configured — drops all mail and logs a warning."""

    def send(self, message: EmailMessage) -> None:
        logger.warning(
            "email_delivery_disabled — configure SMTP_HOST to enable real email delivery. "
            "subject=%r to=%s",
            message.subject,
            message.to,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_email_sender(settings: Settings) -> EmailSender:
    """
    Returns the best available sender:
      - SmtpEmailSender  when SMTP_HOST is configured
      - ConsoleEmailSender  in development with no SMTP
      - DisabledEmailSender  in production with no SMTP
    """
    if settings.smtp_host:
        logger.info(
            "email_provider=smtp host=%s port=%d tls=%s ssl=%s",
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_use_tls,
            settings.smtp_use_ssl,
        )
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=(
                settings.smtp_password.get_secret_value()
                if settings.smtp_password
                else None
            ),
            use_tls=settings.smtp_use_tls,
            use_ssl=settings.smtp_use_ssl,
            from_address=settings.smtp_from_address,
            from_name=settings.smtp_from_name,
        )

    if settings.is_production:
        logger.warning(
            "email_provider=disabled — SMTP_HOST not set. "
            "Verification emails and password reset links will NOT be delivered."
        )
        return DisabledEmailSender()

    logger.info("email_provider=console (dev mode, no SMTP configured)")
    return ConsoleEmailSender()


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
