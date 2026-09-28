"""Validated domain models for typed context relations."""

from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonEmptyTenant = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class RelationType(StrEnum):
    """Initial relation vocabulary for context graph edges."""

    BELONGS_TO = "belongs_to"
    DEPENDS_ON = "depends_on"
    GOVERNS = "governs"
    RELATED_TO = "related_to"
    USES = "uses"


class ContextRelationCreate(BaseModel):
    """Validated input for one directed logical-context relation."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyTenant
    source_logical_id: UUID
    target_logical_id: UUID
    relation_type: RelationType

    @model_validator(mode="after")
    def reject_self_relation(self) -> Self:
        """Prevent meaningless self-edges."""
        if self.source_logical_id == self.target_logical_id:
            raise ValueError("source and target logical context items must differ")
        return self
