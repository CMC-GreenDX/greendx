# Third-party licenses

This register lists every third-party component EcoTrace uses, the exact version we pin, its license and how we use it. It is required by the [project brief](project-brief.md) (rule 5) and by [CONTRIBUTING.md](../CONTRIBUTING.md).

## Policy

- Only components under an [OSI-approved license](https://opensource.org/licenses) are allowed.
- Every component is pinned to an exact version that has been verified to exist in its registry.
- Before adding or upgrading a component, check its current license (licenses change between versions; see [immudb](#rejected-components)) and update this file in the same pull request.
- If a license is unclear, mark it **Uncertain** here and flag it in the pull request instead of guessing.
- Copyleft components (GPL, AGPL) are only run as separate, unmodified containers that EcoTrace talks to over the network. EcoTrace code is never linked into them, so it stays under Apache-2.0. If we ever modify one of them, the modified source must be published under its license.

**How versions and licenses were verified:** the license was read from the project's `LICENSE` file at the pinned tag, or from the GitHub license API for the repository. The version was taken from the project's latest stable release, and the container tag was confirmed to exist in its registry (Docker Hub, quay.io or gcr.io). Last verified: **2026-10-19**.

## EcoTrace itself

| Component | License |
|---|---|
| EcoTrace (this repository) | Apache-2.0, see [LICENSE](../LICENSE) |
| [Code of Conduct](../CODE_OF_CONDUCT.md), adapted from Contributor Covenant 3.0 | CC BY-SA 4.0 (stated in the text's attribution section) |

## Tier 1 core: runtime components

Planned for the `core` Compose profile (Phase 1) unless noted. ✅ means the license is OSI-approved.

| Concern | Component | Pinned version | Artifact | License | How it is used |
|---|---|---|---|---|---|
| Identity, SSO, MFA | Keycloak | 26.8.1 | `quay.io/keycloak/keycloak:26.8.1` | Apache-2.0 ✅ | OIDC provider, issues JWTs with the `tenant_id` claim |
| API gateway | Apache APISIX | 3.19.0 | `apache/apisix:3.19.0-debian` | Apache-2.0 ✅ | JWT validation, rate limiting, routing |
| WAF (stretch) | Coraza proxy-wasm | 0.6.0 | GitHub release `corazawaf/coraza-proxy-wasm` | Apache-2.0 ✅ | Optional WAF loaded as an APISIX Wasm plugin. Last release July 2025; feasibility checked in Phase 1 |
| Secrets | OpenBao | 2.7.1 | `openbao/openbao:2.7.1` | MPL-2.0 ✅ | Secrets store, one path per tenant |
| File quarantine | ClamAV | 1.5.4 | `clamav/clamav:1.5.4` | GPL-2.0 ✅ | Malware scan of every upload; separate container |
| Structured data | PostgreSQL | 18.6 | `postgres:18.6` | PostgreSQL ✅ | OLTP store with row-level security per tenant. PostgreSQL 19 is still at RC1 |
| Auto-generated API | Hasura GraphQL Engine (v2, Community Edition) | v2.50.3 | `hasura/graphql-engine:v2.50.3` | Apache-2.0 ✅ | GraphQL API with permissions based on the tenant claim |
| Object storage | SeaweedFS | 4.48 | `chrislusf/seaweedfs:4.48` | Apache-2.0 ✅ | S3-compatible storage, one bucket per tenant |
| Workflow (BPMN) | Flowable | 8.0.0 | `flowable/flowable-rest:8.0.0` | Apache-2.0 ✅ | Runs BPMN processes deployed from tenant config packs |
| Background jobs | Kestra (open-source edition) | v2.0.6 | `kestra/kestra:v2.0.6` | Apache-2.0 ✅ | Scheduled and batch jobs |
| Event bus | NATS Server with JetStream | 2.15.1 | `nats:2.15.1` | Apache-2.0 ✅ | Domain events in CloudEvents format |
| Tamper-evident ledger | Trillian log server | v1.8.0 | `gcr.io/trillian-opensource-ci/log_server:v1.8.0` | Apache-2.0 ✅ | Append-only Merkle log that seals closed periods. The project is in maintenance mode (see ADR-0001) |
| Tamper-evident ledger | Trillian log signer | v1.8.0 | `gcr.io/trillian-opensource-ci/log_signer:v1.8.0` | Apache-2.0 ✅ | Integrates queued leaves and signs log roots |
| Log shipping | Vector | 0.59.0 | `timberio/vector:0.59.0-debian` | MPL-2.0 ✅ | Collects structured JSON logs, including the audit log of core calls |
| Metrics | Prometheus | v3.15.0 | `prom/prometheus:v3.15.0` | Apache-2.0 ✅ | Metrics collection |
| Dashboards (operations) | Grafana | 13.2.4 | `grafana/grafana:13.2.4` | AGPL-3.0 ✅ | Operational dashboards; separate, unmodified container |
| Backup (k8s phase) | Velero | v1.18.4 | `velero/velero:v1.18.4` | Apache-2.0 ✅ | Cluster backup in Phase 8. The Compose phase uses `pg_dump` from the PostgreSQL image |

### Blocked: decision pending

| Concern | Component | Pinned version | Artifact | License | Problem |
|---|---|---|---|---|---|
| Context broker (IT/OT) | FIWARE Orion-LD | 1.12.0 | `fiware/orion-ld:1.12.0` | AGPL-3.0 ✅ | **Requires MongoDB 4.2 or later. Every such MongoDB release is under the Server Side Public License (SSPL), which is not OSI-approved.** See the open items in [ADR-0001](adr/0001-core-technology-choices.md#open-items). Not needed before Phase 5 |

Candidate replacements under evaluation. Their licenses are verified, but their fit is not yet tested:

| Component | Latest release | License | Notes |
|---|---|---|---|
| Stellio context broker | 2.38.0 | Apache-2.0 ✅ | NGSI-LD broker backed by PostgreSQL |
| Scorpio broker | 6.0.1 | BSD-3-Clause ✅ | NGSI-LD broker backed by PostgreSQL |
| FerretDB + DocumentDB extension | 2.7.0 / v0.117-0 | Apache-2.0 ✅ / MIT ✅ | MongoDB wire-compatible layer on PostgreSQL. Orion-LD compatibility is unverified |

## Optional services (Compose profile `full`)

Not yet verified. Each must be checked and pinned here before it is added: Trino, Apache Iceberg, OpenMetadata, Metabase or Cube, Ollama, Qdrant or Meilisearch, PostGIS.

## Development and CI tools

These are used only to develop and check the repository. They are not shipped with EcoTrace.

| Tool | Pinned version | Source | License | How it is used |
|---|---|---|---|---|
| @commitlint/cli | 21.2.4 | npm | MIT ✅ | Checks commit messages and PR titles |
| @commitlint/config-conventional | 21.2.4 | npm | MIT ✅ | Base Conventional Commits rules |
| markdownlint-cli2 | 0.23.3 | npm | MIT ✅ | Markdown lint |
| git-cliff | 2.14.2 | npm | MIT OR Apache-2.0 ✅ | Generates `CHANGELOG.md` |
| yamllint | 1.38.0 | PyPI | GPL-3.0-or-later ✅ | YAML lint; run as a CLI only, never imported |
| actions/checkout | v7.0.1 (`3d3c42e`) | GitHub Actions | MIT ✅ | CI checkout |
| actions/setup-node | v7.1.0 (`949feb2`) | GitHub Actions | MIT ✅ | CI Node.js setup |
| actions/setup-python | v7.0.0 (`5fda3b9`) | GitHub Actions | MIT ✅ | CI Python setup |

GitHub Actions are pinned to the full commit SHA of the release tag, so a moved tag cannot change what runs in CI.

| Dev environment | Pinned version | Source | License | How it is used |
|---|---|---|---|---|
| Dev container base image | 3.0.9-ubuntu24.04 | `mcr.microsoft.com/devcontainers/base` | MIT ✅ (repository `devcontainers/images`) | Codespaces and VS Code Dev Containers environment |
| Docker-in-Docker feature | 4.1.3 | `ghcr.io/devcontainers/features/docker-in-docker` | MIT ✅ (repository `devcontainers/features`) | Runs Docker Compose inside the codespace |
| SSH server feature | 1.1.0 | `ghcr.io/devcontainers/features/sshd` | MIT ✅ (repository `devcontainers/features`) | Allows `gh codespace ssh` for scripted runs |
| jq, make | Ubuntu 24.04 package versions | apt | MIT ✅, GPL-3.0-or-later ✅ | Demo and health scripts; not pinned beyond the base image release |

Transitive npm dependencies are pinned in `package-lock.json`. As of 2026-10-19, their licenses are MIT, ISC, Apache-2.0, BSD-2-Clause, BSD-3-Clause, Python-2.0 and PSF-2.0 (`argparse`), all OSI-approved.

## Rejected components

| Component | Reason |
|---|---|
| immudb ≥ 1.9DOM.2 (including the current 1.11.2) | The `LICENSE` file changed to Business Source License 1.1 at tag `v1.9DOM.2` (December 2023). BSL is not OSI-approved. The last Apache-2.0 release, `v1.9DOM.1` (November 2023), no longer receives fixes. Replaced by Trillian, see [ADR-0001](adr/0001-core-technology-choices.md) |
| MongoDB ≥ 4.2 | SSPL, not OSI-approved. This blocks Orion-LD (see above) |
| HashiCorp Vault | Business Source License 1.1 (confirmed in the `LICENSE` file on `main`). Replaced by OpenBao |
| Redpanda | Business Source License 1.1 (confirmed in `licenses/bsl.md`). Not used; NATS was chosen |
| n8n | Sustainable Use License, plus `.ee` files under a separate enterprise license. Neither is OSI-approved (confirmed in `LICENSE.md`). Kestra was chosen |
| MinIO | AGPL-3.0, but the GitHub repository is archived (last release `RELEASE.2025-10-15T17-29-55Z`), so no further open-source fixes are expected. SeaweedFS was chosen |
| editorconfig-checker (npm wrapper) | Downloads an unpinned "latest" binary at run time, which breaks the pinned-version rule. Its checks are covered by markdownlint, yamllint and `.gitattributes` |
