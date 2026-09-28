from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.database import build_engine
from contextplane.settings import Settings


def build_record(**overrides: object) -> ContextItemRecord:
    values: dict[str, object] = {
        "id": uuid4(),
        "key": "security.pii.logging",
        "value": {"allowed": False},
        "payload_ref": None,
        "domain": "security",
        "tenant_id": "acme",
        "owner": "security-team",
        "source_type": "manual",
        "source_identifier": "security-policy-2026",
        "authority_level": "mandatory_control",
        "version": 1,
        "effective_from": datetime(2026, 9, 28, tzinfo=UTC),
        "sensitivity": "internal",
        "override_policy": "deny",
        "checksum": "a" * 64,
    }
    values.update(overrides)
    return ContextItemRecord(**values)


@pytest.mark.integration
def test_context_items_table_exists() -> None:
    settings = Settings()
    engine = build_engine(settings)

    try:
        columns = {column["name"] for column in inspect(engine).get_columns("context_items")}
        assert {
            "id",
            "key",
            "domain",
            "tenant_id",
            "source_type",
            "authority_level",
            "version",
            "checksum",
        }.issubset(columns)
    finally:
        engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize(
    "record",
    [
        build_record(version=0),
        build_record(tenant_id=""),
        build_record(checksum="invalid"),
        build_record(value=None, payload_ref=None),
    ],
)
def test_database_constraints_reject_invalid_context(record: ContextItemRecord) -> None:
    settings = Settings()
    engine = build_engine(settings)

    try:
        with Session(engine) as session:
            session.add(record)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()
