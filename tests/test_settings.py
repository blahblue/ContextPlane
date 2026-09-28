import pytest
from pydantic import ValidationError

from contextplane.settings import Settings


def test_settings_accept_explicit_psycopg_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/contextplane",
        _env_file=None,
    )

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_reject_non_postgres_url() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///contextplane.db", _env_file=None)
