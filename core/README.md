# core

Tier 1 headless core: Compose and Kubernetes manifests plus configuration for the core services (identity, gateway, secrets, data, storage, workflow, events, ledger, observability), JSON Schemas and gateway routes.

The core has no end-user UI and contains no business logic. Anything company-specific belongs in `capabilities/`, `apps/` or a tenant config pack under `tenants/`.

Populated from Phase 1.
