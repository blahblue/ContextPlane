# Context Model

## Core entities

### ContextItem

A discrete, versioned piece of governed organizational context.

The initial implementation requires:

- `id`
- `logical_id`
- `supersedes_id`
- `key`
- `value` **or** `payload_ref` (exactly one)
- `domain`
- `scope`
- `owner`
- `source`
- `authority_level`
- `version`
- `effective_from`
- `effective_to`
- `sensitivity`
- `override_policy`
- `checksum`
- `created_at`
- `updated_at`

Application validation and PostgreSQL constraints intentionally overlap for critical invariants.

### Version identity and lineage

`id` identifies one immutable persisted version. `logical_id` identifies the context concept across versions. `supersedes_id` points to the immediately previous persisted version.

The current persistence rules enforce:

- version 1 is a root and has no predecessor;
- later versions must reference a predecessor;
- a version can have at most one direct successor;
- lineage cannot cross tenant or logical-item boundaries;
- `(tenant_id, logical_id, version)` is unique;
- supersession inserts a new row rather than mutating the prior row.

Repository-level supersession additionally requires the key and domain to remain stable and locks the predecessor while creating the next version.

### Initial domains

The MVP intentionally starts with four governed domains:

```text
brand
presentation
engineering
security
```

Expanding the domain set should be an explicit schema decision rather than accepting arbitrary values silently.

### Scope dimensions

A scope always contains a non-empty `tenant_id`. Optional dimensions are:

- business unit
- team
- role
- user
- agent
- application
- repository
- resource
- task
- audience
- environment

The application exposes these as a nested `ContextScope`. Persistence flattens them into indexed/queryable columns so future resolution does not depend on arbitrary JSON traversal.

### Source / provenance

A source has:

- `type`
- `identifier`
- optional `uri`

Initial source types:

```text
manual
git
sharepoint
google_drive
databricks
fabric
api
```

Source text never acquires authority from its wording. Authority is explicit metadata.

### Relation

A typed relationship between context objects or enterprise entities. Relations are planned for PR-006 and are not part of the current schema.

Examples:

```text
team -> belongs_to -> business_unit
repository -> governed_by -> engineering_standard
client_deck -> uses -> external_brand_profile
context_item -> supersedes -> context_item
```

### Policy

A rule controlling visibility, applicability, override behavior, or action. Full policy evaluation is deferred to the policy phase.

### Resolution

An immutable audit representation of a resolved request. Resolution records are deferred until the runtime/audit phase.

## Authority levels

```text
Preference
Recommendation
Standard
Policy
Mandatory Control
```

Authority and scope are independent. A more-specific preference does not automatically override a higher-authority item.

## Sensitivity levels

```text
public
internal
confidential
restricted
```

## Override policy

```text
allow
deny
```

The resolver will later combine override policy with authority and scope specificity.

## Example context object

```yaml
key: brand.logo.primary
value:
  asset_uri: s3://example-brand-assets/logo-primary.svg
domain: brand
scope:
  tenant_id: acme
  audience: external
owner: brand-team
source:
  type: sharepoint
  identifier: brand-standards-2027
  uri: sharepoint://brand/standards/2027
authority_level: standard
effective_from: 2027-01-01T00:00:00Z
effective_to: null
sensitivity: internal
override_policy: deny
checksum: <sha256>
```

## Enforced invariants

The current schema verifies:

- tenant is non-empty;
- key, owner, and source identifier are non-empty;
- exactly one payload representation is present;
- effective timestamps are timezone-aware at the application boundary;
- effective end is later than effective start;
- version is positive and has a valid root/supersession shape;
- supersession lineage remains inside the same tenant and logical item;
- checksum is lowercase SHA-256 hex;
- domain, source type, authority, sensitivity, and override policy use known values.

A subtle PostgreSQL/SQLAlchemy edge case is handled explicitly: JSONB uses `none_as_null=True`, ensuring Python `None` becomes SQL `NULL` so the exactly-one-payload database constraint has the intended semantics.

## Freshness

Freshness behavior is not yet implemented, but the model reserves effective dates for runtime applicability.

Future expectations:

- mandatory policies remain valid until superseded or expired;
- standards can require owner review cadence;
- inferred preferences may lose confidence as they age;
- inferred context should generally expire faster than human-curated authoritative context.
