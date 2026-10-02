"""ContextPlane HTTP application."""

from fastapi import FastAPI

from contextplane.api.publishing import router as publishing_router
from contextplane.api.runtime import router as context_router
from contextplane.http_security import HttpPerimeterConfig, HttpPerimeterMiddleware
from contextplane.models import HealthResponse

_perimeter = HttpPerimeterConfig.from_environment()

app = FastAPI(
    title="ContextPlane",
    version="0.1.0",
    description="Governed organizational context runtime for AI agents.",
    docs_url="/docs" if _perimeter.expose_api_docs else None,
    redoc_url="/redoc" if _perimeter.expose_api_docs else None,
    openapi_url="/openapi.json" if _perimeter.expose_api_docs else None,
)
app.add_middleware(
    HttpPerimeterMiddleware,
    requests_per_minute=_perimeter.requests_per_minute,
    max_tracked_clients=_perimeter.max_tracked_clients,
)
app.include_router(context_router)
app.include_router(publishing_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a minimal liveness response with no external dependencies."""
    return HealthResponse(status="ok")
