# Runtime Resolve API

## Endpoint

```http
POST /v1/context/resolve
Authorization: Bearer <access-token>
Content-Type: application/json
```

The endpoint composes authentication, policy evaluation, context candidate resolution, conflict precedence, and provenance into one runtime response.

## Request

```json
{
  "domains": ["engineering", "security"],
  "keys": ["engineering.api.versioning"],
  "task": "implement_api",
  "audience": "internal",
  "environment": "production"
}
```

### Identity and authorization boundary

The request cannot supply tenant, user, agent, application, repository, resource, role, team, or business-unit identity/scope fields.

ContextPlane derives tenant and principal identity from the validated bearer token. Repository/resource selectors are intentionally deferred until they can be bound to a resource entitlement decision.

Task, audience, and environment are contextual selectors only; they do not grant authorization.

## Processing order

1. Validate bearer token into a normalized ContextPlane principal.
2. Evaluate policy for the requested tenant/domains/keys.
3. Short-circuit if all requested domains are denied.
4. Build resolver scope from the authenticated principal plus permitted contextual selectors.
5. Resolve active, applicable context candidates.
6. Apply policy key narrowing/redaction.
7. Apply deterministic conflict precedence.
8. Load safe provenance for the final records.
9. Return the effective context and explanation traces.

## Response

A successful response contains:

- tenant ID;
- one evaluation timestamp;
- policy decision;
- effective context items;
- safe provenance;
- candidate explanations for winners;
- key-level conflict decisions.

Provenance includes owner, source type, source identifier, and checksum. Raw source URIs are intentionally excluded.

## Status behavior

- `200` — policy evaluation completed, including deny/narrow outcomes.
- `401` — bearer token missing or invalid.
- `409` — unresolved governance conflict at equal precedence.
- `422` — invalid request schema, including attempted identity/resource selector injection.
- `500` — invalid server-side policy configuration or internal invariant failure.
- `503` — reference authentication provider is not configured.

## Reference authentication configuration

The current reference deployment uses the pinned-key Microsoft Entra adapter:

```text
CONTEXTPLANE_ENTRA_TENANT_ID
CONTEXTPLANE_ENTRA_ISSUER
CONTEXTPLANE_ENTRA_AUDIENCE
CONTEXTPLANE_ENTRA_PUBLIC_KEY_PEM
```

Pinned-key validation is intended for local/reference deployments. Remote JWKS discovery and key rotation are deferred.
