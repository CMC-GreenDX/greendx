# dxctl

Onboards and manages tenants from config packs, without code changes ([ADR-0004](../../docs/adr/0004-tenant-model.md)).

```sh
make dxctl ARGS="tenant validate tenants/company-c-cement"
make dxctl ARGS="tenant create tenants/company-c-cement"   # idempotent; prints each step and the time taken
make dxctl ARGS="tenant disable company-c-cement"          # users disabled and logged out; services refuse the tenant
make dxctl ARGS="tenant enable company-c-cement"
make dxctl ARGS="tenant list"
```

`tenant create` does the following:

1. Validates `tenant.yaml`, `org.yaml`, `document-types.yaml` and `emission-sources.yaml` against `core/schemas/`, plus cross-file checks (folder name, departments, document types, fields, facilities).
2. Registers the tenant in `core.tenant` and loads its facilities into `core.facility`.
3. In Keycloak: roles, group `tenant-<id>`, and users with the `tenant_id` attribute. Passwords come from the variable named in `initial_password_env`; otherwise a temporary password is printed once and must be changed at first login.
4. Creates the S3 bucket `ecotrace-<id>`.

`make seed` runs `tenant create` for the demo tenants and is part of `make up`. `make onboarding-check` is the brief's acceptance test: it onboards `company-c-cement`, logs its user in, uploads a document, and disables and re-enables the tenant.

It runs in its own container on the Compose network (`docker compose --profile tools run dxctl`), so it needs no local Python.
