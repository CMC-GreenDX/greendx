# deploy/compose

Docker Compose files with profiles `core`, `app` and `full`, so the core can run on a 16 GB machine without the heavy optional services.

Run everything from the repository root through the Makefile:

```sh
make up       # start the core profile and apply Hasura metadata
make health   # check every service
make demo     # scripted demo, see docs/demo-script.md
make down     # stop, keep data
make reset    # stop and delete data volumes
```

## Services in the core profile today

| Service | Image | Host port | Purpose |
|---|---|---|---|
| `postgres` | `postgres:18.6` | none | OLTP database (`ecotrace`) and Keycloak database |
| `keycloak` | `quay.io/keycloak/keycloak:26.8.1` | 8080 | SSO, issues tokens with the `tenant_id` claim |
| `hasura` | `hasura/graphql-engine:v2.50.3` | 8081 | GraphQL API with per-tenant permissions |
| `apisix` | `apache/apisix:3.19.0-debian` | 9080 | API gateway: JWT verification, rate limiting, routing |

The remaining core services from [ADR-0001](../../docs/adr/0001-core-technology-choices.md) are added in later Phase 1 issues.

## Layout

| Path | Contents |
|---|---|
| `docker-compose.yml` | Service definitions |
| `postgres/` | Database initialisation for core services |
| `health.sh` | Health checks used by `make health` |
| `demo/` | Demo-only data: Keycloak realm with two demo users, sample table, Hasura metadata, demo script. Replaced by tenant config packs and `dxctl` in Phase 2 |

Gateway routes live in [core/gateway/apisix](../../core/gateway/apisix).
