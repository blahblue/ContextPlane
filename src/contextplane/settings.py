"""Application configuration."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ContextPlane runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONTEXTPLANE_",
        extra="ignore",
    )

    database_url: str = ""

    entra_tenant_id: str | None = None
    entra_issuer: str | None = None
    entra_audience: str | None = None
    entra_public_key_pem: str | None = None
    mcp_resource_server_url: str | None = None

    resolution_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600)
    resolution_cache_max_entries: int = Field(default=1024, ge=1, le=100_000)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Require an explicit PostgreSQL URL using the psycopg driver."""
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("database_url must use postgresql+psycopg://")
        return value
