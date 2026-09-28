import os

import pytest

from contextplane.database import build_engine, database_ready
from contextplane.settings import Settings


@pytest.mark.integration
def test_database_is_reachable() -> None:
    database_url = os.getenv("CONTEXTPLANE_DATABASE_URL")
    if database_url is None:
        pytest.skip("CONTEXTPLANE_DATABASE_URL is not configured")

    settings = Settings(database_url=database_url, _env_file=None)
    engine = build_engine(settings)

    try:
        assert database_ready(engine)
    finally:
        engine.dispose()
