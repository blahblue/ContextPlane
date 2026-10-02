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


def test_settings_fail_closed_when_database_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CONTEXTPLANE_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)



def test_database_tls_requirement_rejects_unprotected_url() -> None:
    with pytest.raises(ValidationError, match="database_require_tls"):
        Settings(
            database_url=(
                "postgresql+psycopg://user:pass@db.example.test:5432/contextplane"
            ),
            database_require_tls=True,
            _env_file=None,
        )


@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_database_tls_requirement_accepts_protective_sslmode(sslmode: str) -> None:
    settings = Settings(
        database_url=(
            "postgresql+psycopg://user:pass@db.example.test:5432/"
            f"contextplane?sslmode={sslmode}"
        ),
        database_require_tls=True,
        _env_file=None,
    )

    assert settings.database_require_tls
