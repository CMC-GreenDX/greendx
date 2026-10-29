# ADR-0004: Use one Keycloak realm with a group per tenant, and PostgreSQL row-level security

- **Status:** Proposed (becomes Accepted when the pull request is merged)
- **Date:** 2026-10-22
- **Deciders:** EcoTrace team
- **Issue:** #30

## Context

The brief (section 3.2) asks for an ADR on the tenant model in Keycloak (one realm per tenant, or the Organizations feature) and requires `tenant_id` plus row-level security on every business table. Onboarding must be configuration only, through `dxctl`, in under 5 minutes.

Every service already verifies tokens itself (zero trust): the gateway, Hasura and Document Intake each check the token issuer and signature.

## Decision

1. **Keycloak: one realm `ecotrace` for all tenants.** Each tenant is a group `tenant-<id>` with a `tenant_id` attribute. Each user has a `tenant_id` attribute, which is administrator-only in the user profile, and a token mapper puts it in every access token. Realm roles `uploader`, `reviewer`, `approver` and `tenant-admin` come from `org.yaml`.
2. **PostgreSQL: row-level security on every tenant table** (`core.tenant`, `core.facility`, `intake.*`), with `FORCE ROW LEVEL SECURITY`.
   - Policies compare `tenant_id` with the transaction setting `app.tenant_id`. With no setting, no row matches.
   - Services connect as roles without `BYPASSRLS` (`intake_app`, `ledger_app`) and set the tenant first in every transaction. Schema owners are used only for migrations.
3. **`core.tenant` is the registry.** `dxctl tenant disable` marks a tenant disabled, disables its users and ends their sessions. Services refuse disabled tenants, even with a token issued earlier.
4. **`dxctl tenant create`** is idempotent and only reads the config pack. It validates the pack against the JSON Schemas in `core/schemas/` plus cross-file checks, then creates the registry entry, facilities, Keycloak group, roles and users, and the bucket `ecotrace-<id>`.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| One realm per tenant | Strongest separation of admin consoles and login pages. But every token verifier (APISIX route, Hasura, every service) would need one issuer and JWKS per tenant, and onboarding would have to reconfigure the gateway, which breaks "configuration only, no restart". Keep it for a customer that needs its own identity provider |
| Keycloak Organizations | Fits multi-tenancy, but the `organization` claim is a list and would need extra mapping in every verifier. A group with an attribute gives the same result with a single string claim |
| Isolation in application code only | One forgotten `WHERE tenant_id = …` leaks data. RLS makes the database the last line of defence (`make rls-check`) |

## Consequences

- Isolation now has four independent layers: gateway (signature), service (tenant claim and registry status), queries (tenant filter) and PostgreSQL (RLS).
- Hasura still connects as the owner and relies on its own permission rules. Moving Hasura behind RLS (session variables in SQL) is a follow-up.
- Tenant administrators cannot get their own Keycloak admin console. Self-service administration would come from a tenant-scoped admin API.
- OpenBao secret paths per tenant and BPMN deployment are added to `dxctl` when those services land.
