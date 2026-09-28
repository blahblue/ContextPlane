from uuid import uuid4

import pytest
from pydantic import ValidationError

from contextplane.context_graph import ContextRelationCreate, RelationType


def test_relation_create_accepts_known_type() -> None:
    relation = ContextRelationCreate(
        tenant_id=" acme ",
        source_logical_id=uuid4(),
        target_logical_id=uuid4(),
        relation_type=RelationType.GOVERNS,
    )

    assert relation.tenant_id == "acme"
    assert relation.relation_type is RelationType.GOVERNS


def test_relation_create_rejects_self_edge() -> None:
    logical_id = uuid4()

    with pytest.raises(ValidationError, match="must differ"):
        ContextRelationCreate(
            tenant_id="acme",
            source_logical_id=logical_id,
            target_logical_id=logical_id,
            relation_type=RelationType.RELATED_TO,
        )


def test_relation_create_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        ContextRelationCreate(
            tenant_id="acme",
            source_logical_id=uuid4(),
            target_logical_id=uuid4(),
            relation_type="invented",  # type: ignore[arg-type]
        )
