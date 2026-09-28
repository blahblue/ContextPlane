"""Shared API models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health endpoint response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
