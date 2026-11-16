import hashlib
import hmac

from app.core.config import Settings
from app.providers.payments.base import PaymentProvider
from app.providers.payments.fake import FakeProvider


def build_payment_providers(settings: Settings) -> dict[str, PaymentProvider]:
    """name -> provider. A real provider is registered here once chosen (not decided yet)."""
    providers: dict[str, PaymentProvider] = {}
    if settings.payment_provider == "fake":
        # Derived from the JWT secret, so no secret is ever hard-coded in source.
        secret = hmac.new(
            settings.jwt_secret_key.get_secret_value().encode(),
            b"fake-payment-provider-webhook",
            hashlib.sha256,
        ).digest()
        providers["fake"] = FakeProvider(
            secret, tolerance_seconds=settings.payment_webhook_tolerance_seconds
        )
    return providers
