# Context Model

## Core entities

### ContextItem

A discrete piece of organizational context.

Required fields should include:

- `id`
- `key`
- `value` or `payload_ref`
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
- `created_at`
- `updated_at`
- `checksum`

### Scope dimensions

- tenant
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

### Relation

Typed relationship between context objects or enterprise entities.

Examples:

```text
team -> belongs_to -> business_unit
repository -> governed_by -> engineering_standard
client_deck -> uses -> external_brand_profile
context_item -> supersedes -> context_item
```

### Source

Provenance information for the authoritative origin.

### Policy

Rule controlling visibility, applicability, override behavior, or action.

### Resolution

Immutable audit representation of a resolved request.

## Authority levels

```text
Preference
Recommendation
Standard
Policy
Mandatory Control
```

Authority and scope are independent. A user preference may be more specific than an organization standard but still may not override it if the standard forbids override.

## Example context object

```yaml
id: ctx_brand_external_logo_008
key: brand.logo.primary
value:
  asset_uri: s3://example-brand-assets/logo-primary.svg
domain: brand
scope:
  tenant: acme
  audience: external
owner: brand-team
source:
  type: sharepoint
  uri: sharepoint://brand/standards/2027
authority_level: standard
version: 8
effective_from: 2027-01-01
effective_to: null
sensitivity: internal
override_policy: deny
```

## Example resolved bundle

```yaml
resolution_id: res_123
principal:
  user: user_42
  agent: cursor_agent_19
request:
  task: implement_api
  repository: checkout-api
context:
  - key: engineering.api.versioning
    value: semantic-versioning
    authority: standard
  - key: security.pii.logging
    value: prohibited
    authority: mandatory_control
explanation:
  - item: security.pii.logging
    reason: matched org security policy + production environment
```

## Freshness

- mandatory policies remain valid until superseded or expired;
- standards should support owner review cadence;
- preferences may lose confidence as they age;
- inferred context should expire faster than human-curated context.

The MVP should model freshness metadata even if automated decay is deferred.
