"""ContextPlane HTTP application."""

from fastapi import FastAPI

from contextplane.models import HealthResponse

app = FastAPI(
    title="ContextPlane",
    version="0.1.0",
    description="Governed organizational context runtime for AI agents.",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a minimal liveness response with no external dependencies."""
    return HealthResponse(status="ok")
