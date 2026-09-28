from copy import deepcopy
from pathlib import Path

import pytest

from contextplane.context_registry import ContextDomain
from contextplane.context_registry.seed import SeedFileError, load_seed_document

FIXTURE = Path("examples/context/mvp.yaml")


def test_mvp_seed_contains_all_four_domains() -> None:
    items = load_seed_document(FIXTURE)

    assert {item.domain for item in items} == {
        ContextDomain.BRAND,
        ContextDomain.PRESENTATION,
        ContextDomain.ENGINEERING,
        ContextDomain.SECURITY,
    }


def test_seed_checksum_is_deterministic_across_mapping_order(tmp_path: Path) -> None:
    original = load_seed_document(FIXTURE)[0]

    reordered = {
        "items": [
            {
                "source": {"identifier": original.source.identifier, "type": "manual"},
                "owner": original.owner,
                "scope": {
                    "audience": original.scope.audience,
                    "tenant_id": original.scope.tenant_id,
                },
                "effective_from": "2026-09-28T00:00:00Z",
                "override_policy": original.override_policy.value,
                "sensitivity": original.sensitivity.value,
                "authority_level": original.authority_level.value,
                "domain": original.domain.value,
                "value": deepcopy(original.value),
                "key": original.key,
            }
        ]
    }
    path = tmp_path / "reordered.yaml"
    import yaml

    path.write_text(yaml.safe_dump(reordered, sort_keys=False), encoding="utf-8")
    parsed = load_seed_document(path)[0]

    assert parsed.checksum == original.checksum


def test_duplicate_source_identity_is_rejected_before_apply(tmp_path: Path) -> None:
    import yaml

    base = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    duplicate = deepcopy(base["items"][0])
    base["items"].append(duplicate)

    path = tmp_path / "duplicate.yaml"
    path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    with pytest.raises(SeedFileError, match="duplicate seed source identity"):
        load_seed_document(path)


def test_seed_document_rejects_unknown_top_level_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("items: []\nunexpected: true\n", encoding="utf-8")

    with pytest.raises(SeedFileError, match="exactly one top-level"):
        load_seed_document(path)
