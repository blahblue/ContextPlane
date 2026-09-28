from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.seed import load_seed_file
from contextplane.database import build_engine
from contextplane.settings import Settings

FIXTURE = Path("examples/context/mvp.yaml")


@pytest.mark.integration
def test_seed_load_is_idempotent() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = load_seed_file(session, FIXTURE)
            session.commit()

        with Session(engine) as session:
            second = load_seed_file(session, FIXTURE)
            row_count = session.scalar(select(func.count()).select_from(ContextItemRecord))
            session.commit()

        assert [result.status for result in first] == ["created"] * 4
        assert [result.status for result in second] == ["unchanged"] * 4
        assert row_count == 4
    finally:
        engine.dispose()


@pytest.mark.integration
def test_changed_seed_content_creates_new_immutable_version(tmp_path: Path) -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = load_seed_file(session, FIXTURE)
            original = next(
                result
                for result in first
                if result.source_identifier == "mvp-engineering-api-versioning"
            )
            session.commit()

        data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
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
                        ContextItemRecord.tenant_id == "demo-org",
                        ContextItemRecord.source_identifier
                        == "mvp-engineering-api-versioning",
                    )
                    .order_by(ContextItemRecord.version)
                )
            )
            session.commit()

        assert original.version == 1
        assert changed_result.status == "superseded"
        assert changed_result.version == 2
        assert changed_result.checksum != original.checksum
        assert [record.version for record in versions] == [1, 2]
        assert versions[0].value == {"scheme": "semantic"}
        assert versions[1].value == {"scheme": "calendar"}
    finally:
        engine.dispose()
