from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import SlidingWindowRateLimiter
from app.modules.health.router import router as health_router
from app.providers.email import build_email_sender
from app.providers.payments.factory import build_payment_providers
from app.providers.scanner import build_scanner
from app.providers.storage.factory import build_storage


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # add_middleware: the LAST one added is the OUTERMOST.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    register_exception_handlers(app)

    # Process-wide collaborators live on app.state so tests can swap them.
    app.state.rate_limiter = SlidingWindowRateLimiter(enabled=settings.rate_limit_enabled)
    app.state.email_sender = build_email_sender(settings)
    app.state.storage = build_storage(settings)
    app.state.scanner = build_scanner(settings.malware_scanner)
    app.state.payment_providers = build_payment_providers(settings)

    # Unversioned probes for the hosting platform; versioned routes for clients.
    app.include_router(health_router, include_in_schema=False)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app
