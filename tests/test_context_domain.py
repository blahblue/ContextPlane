from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextItemCreate,
    ContextScope,
    ContextSource,
    OverridePolicy,
    SensitivityLevel,
    SourceType,
)


def valid_item(**overrides: object) -> ContextItemCreate:
    payload: dict[str, object] = {
        "key": "security.pii.logging",
        "value": {"allowed": False},
        "domain": ContextDomain.SECURITY,
        "scope": ContextScope(tenant_id="acme", environment="production"),
        "owner": "security-team",
        "source": ContextSource(
            type=SourceType.MANUAL,
            identifier="security-policy-2026",
        ),
        "authority_level": AuthorityLevel.MANDATORY_CONTROL,
        "effective_from": datetime(2026, 9, 28, tzinfo=UTC),
        "sensitivity": SensitivityLevel.INTERNAL,
        "override_policy": OverridePolicy.DENY,
        "checksum": "a" * 64,
    }
    payload.update(overrides)
    return ContextItemCreate.model_validate(payload)


def test_context_item_accepts_structured_value() -> None:
    item = valid_item()

    assert item.scope.tenant_id == "acme"
    assert item.authority_level is AuthorityLevel.MANDATORY_CONTROL


def test_context_item_accepts_payload_reference() -> None:
    item = valid_item(value=None, payload_ref="asset://brand/logo-primary.svg")

    assert item.payload_ref is not None


@pytest.mark.parametrize(
    ("value", "payload_ref"),
    [
        (None, None),
        ({"foo": "bar"}, "asset://duplicate"),
    ],
)
def test_context_item_requires_exactly_one_payload(
    value: object,
    payload_ref: object,
) -> None:
    with pytest.raises(ValidationError):
        valid_item(value=value, payload_ref=payload_ref)


def test_context_item_rejects_inverted_effective_window() -> None:
    start = datetime(2026, 9, 28, tzinfo=UTC)

    with pytest.raises(ValidationError):
        valid_item(effective_from=start, effective_to=start - timedelta(seconds=1))


def test_context_item_requires_timezone_aware_dates() -> None:
    with pytest.raises(ValidationError):
        valid_item(effective_from=datetime(2026, 9, 28))


def test_context_item_rejects_invalid_checksum() -> None:
    with pytest.raises(ValidationError):
        valid_item(checksum="not-a-sha256")


def test_scope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ContextScope.model_validate({"tenant_id": "acme", "unknown": "value"})
