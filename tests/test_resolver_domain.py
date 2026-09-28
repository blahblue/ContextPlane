from datetime import datetime

import pytest
from pydantic import ValidationError

from contextplane.context_registry import ContextDomain, ContextScope
from contextplane.resolver import ContextResolutionRequest


def test_resolution_request_normalizes_tenant_scope() -> None:
    request = ContextResolutionRequest(
        scope=ContextScope(tenant_id=" acme ", team=" platform "),
        domains={ContextDomain.ENGINEERING},
    )

    assert request.scope.tenant_id == "acme"
    assert request.scope.team == "platform"
    assert request.domains == frozenset({ContextDomain.ENGINEERING})


def test_resolution_request_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ContextResolutionRequest(
            scope=ContextScope(tenant_id="acme"),
            as_of=datetime(2026, 9, 28, 12, 0, 0),
        )
