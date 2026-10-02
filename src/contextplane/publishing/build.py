"""Canonical construction helpers shared by direct and approval-gated publishing."""

import hashlib
import json
from uuid import UUID

from contextplane.auth import Principal
from contextplane.context_registry.domain import (
    ContextItemCreate,
    ContextScope,
    ContextSource,
    SourceType,
)
from contextplane.publishing.domain import PublicationAction, PublishContextRequest


def sha256_text(value: str) -> str:
    """Return a lowercase hexadecimal SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    """Serialize semantic content deterministically for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def build_authenticated_context_item(
    *,
    principal: Principal,
    request: PublishContextRequest,
) -> ContextItemCreate:
    """Inject authenticated tenant and server-owned API provenance."""
    scope = ContextScope(
        tenant_id=principal.tenant_id,
        **request.scope.model_dump(),
    )
    provisional = ContextItemCreate(
        key=request.key,
        value=request.value,
        payload_ref=request.payload_ref,
        domain=request.domain,
        scope=scope,
        owner=request.owner,
        source=ContextSource(
            type=SourceType.API,
            identifier=request.source.identifier,
            uri=request.source.uri,
        ),
        authority_level=request.authority_level,
        effective_from=request.effective_from,
        effective_to=request.effective_to,
        sensitivity=request.sensitivity,
        override_policy=request.override_policy,
        checksum="0" * 64,
    )
    semantic = provisional.model_dump(mode="json", exclude={"checksum"})
    checksum = sha256_text(canonical_json(semantic))
    return provisional.model_copy(update={"checksum": checksum})


def publication_request_hash(
    *,
    action: PublicationAction,
    previous_id: UUID | None,
    item: ContextItemCreate,
) -> str:
    """Hash one normalized publication intent."""
    return sha256_text(
        canonical_json(
            {
                "action": action.value,
                "previous_id": str(previous_id) if previous_id is not None else None,
                "item": item.model_dump(mode="json"),
            }
        )
    )
