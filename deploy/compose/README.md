# deploy/compose

The `core` profile starts the implemented services below on a 16 GB machine. The `tools` profile runs the tenant CLI on demand; `app` and `full` are reserved for future profiles.

Run everything from the repository root through the Makefile:

```sh
make up       # start the core profile and apply Hasura metadata
make health   # check every service
make demo     # scripted demo, see docs/demo-script.md
make down     # stop, keep data
make reset    # stop and delete data volumes
```

`make up` first runs `make trillian-schema`. This downloads Trillian's database schema from its pinned release (v1.8.0) and refuses it if its SHA-256 does not match. The schema is not copied into this repository. If you run `docker compose` directly, run `make trillian-schema` once before.

## Services in the core profile

| Service | Image | Host port | Purpose |
|---|---|---|---|
| `postgres` | `postgres:18.6` | none | OLTP database (`ecotrace`) and Keycloak database |
| `keycloak` | `quay.io/keycloak/keycloak:26.8.1` | 8080 | SSO, issues tokens with the `tenant_id` claim |
| `hasura` | `hasura/graphql-engine:v2.50.3` | 8081 | GraphQL API with per-tenant permissions |
| `apisix` | `apache/apisix:3.19.0-debian` | 9080 | API gateway: JWT verification, rate limiting, routing |
| `nats` | `nats:2.15.1` | none | Event bus (JetStream), stream `ECOTRACE_EVENTS` |
| `seaweedfs` | `chrislusf/seaweedfs:4.48` | none | S3 object storage, one bucket per tenant |
| `clamav` | `clamav/clamav:1.5.4` | none | Malware scan of every upload (first start downloads signatures) |
| `document-intake` | built from `capabilities/document-intake` | none (via gateway `/intake/*`) | Document classification and extraction |
| `demo-console` | `nginx:1.30.6-alpine` | none (via gateway `/`) | Static demo console |
| `db-migrate` | `postgres:18.6` | none | Applies the database schema, then exits |
| `trillian-log-server`, `trillian-log-signer` | `gcr.io/trillian-opensource-ci/log_server:v1.8.0`, `log_signer:v1.8.0` | none | Tamper-evident log, one tree per tenant |
| `ledger-sealer` | built from `apps/ledger-sealer` | none | Writes period seals to Trillian and verifies them |
| `flowable` | `flowable/flowable-rest:8.0.0` | none | BPMN engine |
| `workflow` | built from `capabilities/workflow-ui` | none (via gateway) | Task inbox and BPMN deployment per tenant |
| `carbon-ledger` | built from `apps/carbon-ledger` | none (via gateway `/ledger/*`) | Activity records, emissions, lineage, period close |
| `purchase-approval` | built from `apps/purchase-approval` | none (via gateway) | Purchase invoice approvals |
| `api-docs` | `swaggerapi/swagger-ui:v5.33.3` | none (via gateway `/api-docs/`) | API reference |

The `dxctl` CLI is separate from these services: it runs on demand in the `tools` profile, built from `tools/dxctl`, with no host port. `make up` uses it to configure the portal and seed Companies A and B. Company C has an additional example pack for the onboarding demo.

OpenBao, Kestra and observability from [ADR-0001](../../docs/adr/0001-core-technology-choices.md) are planned for v1.0.0.

## Layout

| Path | Contents |
|---|---|
| `docker-compose.yml` | Service definitions |
| `postgres/` | Database initialisation for core services |
| `health.sh` | Health checks used by `make health` |
| `demo/` | Keycloak realm, Hasura metadata and the check scripts behind `make demo`, `make health` and the other `make *-check` targets |

Gateway routes live in [core/gateway/apisix](../../core/gateway/apisix).
