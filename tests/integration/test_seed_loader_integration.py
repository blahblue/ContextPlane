from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.seed import load_seed_file
from contextplane.database import build_engine
from contextplane.settings import Settings

FIXTURE = Path("examples/context/mvp.yaml")


def tenant_fixture(tmp_path: Path, tenant_id: str) -> Path:
    """Write an isolated copy of the MVP seed for one integration test tenant."""
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    for item in data["items"]:
        item["scope"]["tenant_id"] = tenant_id

    path = tmp_path / "seed.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.integration
def test_seed_load_is_idempotent(tmp_path: Path) -> None:
    engine = build_engine(Settings())
    tenant_id = f"seed-idempotent-{uuid4()}"
    fixture = tenant_fixture(tmp_path, tenant_id)

    try:
        with Session(engine) as session:
            first = load_seed_file(session, fixture)
            session.commit()

        with Session(engine) as session:
            second = load_seed_file(session, fixture)
            row_count = session.scalar(
                select(func.count())
                .select_from(ContextItemRecord)
                .where(ContextItemRecord.tenant_id == tenant_id)
            )
            session.commit()

        assert [result.status for result in first] == ["created"] * 4
        assert [result.status for result in second] == ["unchanged"] * 4
        assert row_count == 4
    finally:
        engine.dispose()


@pytest.mark.integration
def test_changed_seed_content_creates_new_immutable_version(tmp_path: Path) -> None:
    engine = build_engine(Settings())
    tenant_id = f"seed-version-{uuid4()}"
    fixture = tenant_fixture(tmp_path, tenant_id)

    try:
        with Session(engine) as session:
            first = load_seed_file(session, fixture)
            original = next(
                result
                for result in first
                if result.source_identifier == "mvp-engineering-api-versioning"
            )
            session.commit()

        data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        engineering = next(
            item
            for item in data["items"]
            if item["source"]["identifier"] == "mvp-engineering-api-versioning"
        )
        engineering["value"]["scheme"] = "calendar"

        changed = tmp_path / "changed.yaml"
        changed.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        with Session(engine) as session:
            second = load_seed_file(session, changed)
            changed_result = next(
                result
                for result in second
                if result.source_identifier == "mvp-engineering-api-versioning"
            )
            versions = list(
                session.scalars(
                    select(ContextItemRecord)
                    .where(
                        ContextItemRecord.tenant_id == tenant_id,
                        ContextItemRecord.source_identifier
                        == "mvp-engineering-api-versioning",
                    )
                    .order_by(ContextItemRecord.version)
                )
            )
            version_snapshot = [
                (record.version, record.value)
                for record in versions
            ]
            session.commit()

        assert original.version == 1
        assert changed_result.status == "superseded"
        assert changed_result.version == 2
        assert changed_result.checksum != original.checksum
        assert version_snapshot == [
            (1, {"scheme": "semantic"}),
            (2, {"scheme": "calendar"}),
        ]
    finally:
        engine.dispose()
