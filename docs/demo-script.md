# Demo script

This script covers the **core slice** delivered for the organiser demo on 2026-10-22: identity (Keycloak), API gateway (APISIX), structured data (PostgreSQL and Hasura) and tenant isolation. The full product demo from the [project brief](project-brief.md) (section 11) is added phase by phase.

## Before the demo (10 minutes ahead)

1. Open the codespace: on GitHub, **Code → Codespaces → ecotrace-demo**. Opening it in **VS Code desktop** (Codespaces extension) is recommended, because then the forwarded ports work on `localhost` in your own browser.
2. In the codespace terminal:

   ```sh
   make up      # starts PostgreSQL, Keycloak, Hasura, APISIX and applies Hasura metadata
   make health  # every line must say OK
   ```

   The first start downloads the images and takes a few minutes. Later starts take about one minute.
3. Do a dry run with `make demo`. Every step must print `PASS`.

If something fails: `make logs` shows the service logs, and `make reset && make up` starts again from an empty database.

## Live demo

Run `DEMO_PAUSE=1 make demo` so the script waits for Enter after each step.

| Step | What the audience sees | What to say |
|---|---|---|
| 1 | `HTTP 401` for a call without a token | Zero trust at the edge: the gateway rejects every call that has no valid token, before it reaches any service. |
| 2 | Alice's token contains `tenant_id: company-a-steel`; the API returns only Company A's three facilities | One login (Keycloak SSO) gives a signed token that carries the tenant. The gateway checks the signature; Hasura checks it again and filters rows by tenant. |
| 3 | Bob (`company-b-logistics`) sees only Company B's facilities | Same core, same code, different company: tenants are separated by configuration, not by code. |
| 4 | `HTTP 401` for a token whose tenant was changed by hand | A user cannot switch tenants by editing the token: the signature no longer matches. |

## Optional: show the consoles

| Console | URL | Login |
|---|---|---|
| Keycloak (users, `tenant_id` attribute, token mapper) | <http://localhost:8080/admin/master/console/#/ecotrace> | `admin` / `KC_ADMIN_PASSWORD` from `.env` |
| Hasura (the `demo.facility` table and its row filter `tenant_id = X-Hasura-Tenant-Id`) | <http://localhost:8081/console> | `HASURA_ADMIN_SECRET` from `.env` |

Keycloak redirects to `localhost:8080`, so its console works when the codespace is opened in VS Code desktop. In the browser-only codespace, use the Hasura console only.

## What is not in this demo yet

Be ready to answer these honestly:

- **Row-level security in PostgreSQL** (Phase 2). Today isolation is enforced by the gateway (signature) and by Hasura permissions; database-level RLS is added next.
- **One realm per tenant and `dxctl` onboarding** (Phase 2). Today both demo users live in one realm.
- **The other core services** (OpenBao, SeaweedFS, NATS JetStream, Flowable, Kestra, Trillian, ClamAV, observability) are the remaining Phase 1 work. Their choices and licenses are in [ADR-0001](adr/0001-core-technology-choices.md) and [docs/licenses.md](licenses.md).
