from typing import Literal

from pydantic import BaseModel


class HealthData(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessData(BaseModel):
    status: Literal["ready"]
    checks: dict[str, str]
