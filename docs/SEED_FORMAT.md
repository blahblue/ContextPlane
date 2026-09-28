# Seed File Format

ContextPlane uses YAML seed files for deterministic local development, demos, and resolver fixtures.

Seed files are **operator-controlled bootstrap inputs**, not a general ingestion format for arbitrary enterprise documents.

## Structure

A seed document contains exactly one top-level key:

```yaml
items:
  - key: engineering.api.versioning
    value:
      scheme: semantic
    domain: engineering
    scope:
      tenant_id: demo-org
      environment: production
    owner: architecture-team
    source:
      type: manual
      identifier: mvp-engineering-api-versioning
    authority_level: standard
    effective_from: "2026-09-28T00:00:00Z"
    sensitivity: internal
    override_policy: deny
```

The loader computes the SHA-256 checksum. Seed files must not rely on a caller-supplied checksum.

## Stable seed identity

For seed loading only, the stable logical seed identity is:

```text
tenant_id + source.type + source.identifier
```

Therefore `source.identifier` must be stable and unique for each seeded logical context item within a tenant and source type.

If the same seed identity already exists:

- identical canonical content -> no-op;
- changed canonical content -> new immutable version;
- multiple logical histories -> fail closed as ambiguous.

This identity rule is intentionally specific to the seed loader. Future source connectors may use connector-specific external IDs rather than overloading general provenance fields.

## Canonical checksums

ContextPlane validates the item first, serializes normalized semantic content to canonical JSON, excludes the checksum field, and calculates SHA-256.

This means superficial YAML mapping order does not create a new version.

Changes to governed content, scope, owner, provenance, authority, effective dates, sensitivity, or override policy do change the checksum.

## Transaction behavior

The loader does not commit database transactions.

All items are parsed and validated before writes begin. The caller controls commit or rollback, so a failure during application can roll back the whole seed operation.

## Security properties

- YAML uses `safe_load`.
- Unknown top-level document keys are rejected.
- Pydantic rejects unknown item/scope/source fields.
- Duplicate seed identities in one file are rejected before writes.
- Ambiguous database identity mappings fail closed.
- Existing immutable versioning and tenant-scoped repository constraints remain authoritative.

## Example corpus

The reference four-domain fixture is:

```text
examples/context/mvp.yaml
```

It includes brand, presentation, engineering, and security context.
