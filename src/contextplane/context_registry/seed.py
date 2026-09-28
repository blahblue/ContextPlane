"""Load governed context seed files into the immutable registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import ContextItemCreate
from contextplane.context_registry.repository import (
    create_context_item,
    supersede_context_item,
)

SeedStatus = Literal["created", "unchanged", "superseded"]


class SeedFileError(ValueError):
    """Raised when a seed document is invalid or ambiguous."""


@dataclass(frozen=True)
class SeedResult:
    """Result of applying one seed entry."""

    source_identifier: str
    tenant_id: str
    key: str
    status: SeedStatus
    version: int
    checksum: str


def _canonical_checksum(item: ContextItemCreate) -> str:
    """Hash normalized semantic content while excluding the checksum itself."""
    payload = item.model_dump(mode="json", exclude={"checksum"})
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_seed_item(raw: object) -> ContextItemCreate:
    """Validate and normalize one raw YAML context item."""
    if not isinstance(raw, dict):
        raise SeedFileError("each seed item must be a mapping")

    candidate = dict(raw)
    candidate["checksum"] = "0" * 64

    try:
        parsed = ContextItemCreate.model_validate(candidate)
    except ValidationError as exc:
        raise SeedFileError(str(exc)) from exc

    return parsed.model_copy(update={"checksum": _canonical_checksum(parsed)})


def load_seed_document(path: str | Path) -> list[ContextItemCreate]:
    """Parse and validate all items before any database writes occur."""
    seed_path = Path(path)

    try:
        data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SeedFileError(f"unable to read seed file: {seed_path}") from exc

    if not isinstance(data, dict) or set(data) != {"items"}:
        raise SeedFileError("seed document must contain exactly one top-level 'items' key")

    raw_items = data["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise SeedFileError("'items' must be a non-empty list")

    items = [_validate_seed_item(raw) for raw in raw_items]

    identities: set[tuple[str, str, str]] = set()
    for item in items:
        identity = (
            item.scope.tenant_id,
            item.source.type.value,
            item.source.identifier,
        )
        if identity in identities:
            raise SeedFileError(
                "duplicate seed source identity: "
                f"{identity[0]}/{identity[1]}/{identity[2]}"
            )
        identities.add(identity)

    return items


def _find_latest_seed_record(
    session: Session,
    *,
    item: ContextItemCreate,
) -> ContextItemRecord | None:
    """Return the latest version for one unambiguous tenant/source seed identity."""
    identity_filter = (
        ContextItemRecord.tenant_id == item.scope.tenant_id,
        ContextItemRecord.source_type == item.source.type.value,
        ContextItemRecord.source_identifier == item.source.identifier,
    )
    logical_ids = list(
        session.scalars(
            select(ContextItemRecord.logical_id)
            .where(*identity_filter)
            .distinct()
        )
    )
    if len(logical_ids) > 1:
        raise SeedFileError(
            "seed source identity maps to multiple logical context items: "
            f"{item.scope.tenant_id}/{item.source.type.value}/{item.source.identifier}"
        )

    return session.scalar(
        select(ContextItemRecord)
        .where(*identity_filter)
        .order_by(ContextItemRecord.version.desc())
        .limit(1)
        .with_for_update()
    )


def apply_seed_items(
    session: Session,
    items: list[ContextItemCreate],
) -> list[SeedResult]:
    """Apply validated seed items without committing the caller's transaction."""
    results: list[SeedResult] = []

    for item in items:
        current = _find_latest_seed_record(session, item=item)

        if current is None:
            record = create_context_item(session, item)
            status: SeedStatus = "created"
        elif current.checksum == item.checksum:
            record = current
            status = "unchanged"
        else:
            record = supersede_context_item(
                session,
                tenant_id=item.scope.tenant_id,
                previous_id=current.id,
                replacement=item,
            )
            status = "superseded"

        results.append(
            SeedResult(
                source_identifier=item.source.identifier,
                tenant_id=item.scope.tenant_id,
                key=item.key,
                status=status,
                version=record.version,
                checksum=record.checksum,
            )
        )

    return results


def load_seed_file(session: Session, path: str | Path) -> list[SeedResult]:
    """Parse, validate, and apply a seed file within the caller's transaction."""
    return apply_seed_items(session, load_seed_document(path))
