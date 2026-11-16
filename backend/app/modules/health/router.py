from fastapi import APIRouter

from app import __version__
from app.core.deps import DbSession
from app.core.errors import ServiceUnavailableError
from app.core.responses import Envelope, ErrorEnvelope, ok
from app.modules.health.schemas import HealthData, ReadinessData
from app.modules.health.service import check_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Envelope[HealthData], summary="Liveness probe")
async def health() -> Envelope[HealthData]:
    return ok(HealthData(status="ok", service="oars-api", version=__version__))


@router.get(
    "/ready",
    response_model=Envelope[ReadinessData],
    responses={503: {"model": ErrorEnvelope}},
    summary="Readiness probe (checks the database)",
)
def ready(db: DbSession) -> Envelope[ReadinessData]:
    if not check_database(db):
        raise ServiceUnavailableError("Service is not ready.", code="not_ready")
    return ok(ReadinessData(status="ready", checks={"database": "ok"}))
