# ADR-0001: Choose the Tier 1 core technology stack

- **Status:** Proposed (becomes Accepted when the pull request is merged)
- **Date:** 2026-10-19
- **Deciders:** EcoTrace team
- **Issue:** #7

## Context

The Tier 1 core must provide identity and SSO, an API gateway, structured and unstructured data, workflow, events and a tamper-evident ledger to any application and any tenant. It is half of the grade and must move from Company A to Company B without code changes ([project brief](../project-brief.md), sections 1–3).

Constraints that drive every choice below:

1. **OSI-approved licenses only.** Several well-known components changed license recently, so every candidate was re-checked at its pinned version. Details are in [docs/licenses.md](../licenses.md).
2. **Runs on a 16 GB student laptop** with Docker Compose. Heavy services must be optional.
3. **Multi-tenant by configuration.** Each component must support per-tenant isolation (realm, row-level security, bucket, secrets path, event subject).
4. **Defensible in front of a jury.** We prefer components with a clear, well-known story over niche ones.

The brief already fixes most components. This ADR records the three choices the brief left open (event bus, object storage, ledger after the immudb license change) and confirms the rest.

## Decision

| Concern | Choice | Version |
|---|---|---|
| Identity, SSO, MFA | Keycloak | 26.8.1 |
| API gateway | Apache APISIX (Coraza WAF as a stretch goal) | 3.19.0 |
| Secrets | OpenBao | 2.7.1 |
| File quarantine | ClamAV | 1.5.4 |
| Structured data | PostgreSQL | 18.6 |
| Auto-generated API | Hasura GraphQL Engine v2 | v2.50.3 |
| Object storage | **SeaweedFS** | 4.48 |
| Workflow (BPMN) | Flowable | 8.0.0 |
| Background jobs | Kestra | v2.0.6 |
| Event bus | **NATS JetStream** | 2.15.1 |
| Tamper-evident ledger | **Trillian** (log server and log signer) | v1.8.0 |
| Context broker | FIWARE Orion-LD, **blocked**, see [Open items](#open-items) | 1.12.0 |
| Logs and metrics | Vector, Prometheus, Grafana | 0.59.0, v3.15.0, 13.2.4 |
| Backup | `pg_dump` plus bucket sync (Compose); Velero (Kubernetes) | —, v1.18.4 |

### 1. Event bus: NATS JetStream

NATS JetStream carries all domain events (`document.received`, `document.extracted`, `ledger.sealed`, and so on) in CloudEvents format.

- A single NATS server uses tens of megabytes of RAM, against roughly 1 GB or more for a Kafka broker. That matters on a 16 GB laptop that also runs Keycloak, Flowable, Kestra and PostgreSQL.
- JetStream provides persistent streams, replay and durable consumers, which is what Carbon Ledger and Purchase Approval need to subscribe independently to `document.extracted`.
- CloudEvents defines a NATS protocol binding, so events keep a standard envelope.
- Hierarchical subjects (for example `<tenant>.document.extracted`) make per-tenant routing and permissions straightforward. The exact tenant-isolation scheme (subject prefix or header) is decided in a Phase 2 ADR, as the brief requires.

### 2. Object storage: SeaweedFS

SeaweedFS provides the S3-compatible store for uploaded documents and cold-period exports, with one bucket per tenant.

- Apache-2.0, the same license as EcoTrace, so there are no copyleft questions.
- Actively released (4.48 in September 2026). It runs as a single container in development and scales out later.
- MinIO, the usual default, is ruled out because its GitHub repository is now archived.

### 3. Tamper-evident ledger: Trillian instead of immudb

At period close, Carbon Ledger appends the hash of every approved emission entry to a Trillian log and stores the signed log root. Verification recomputes each hash from PostgreSQL and checks its inclusion proof against the signed root. A tampered row produces a different hash, so its proof fails. This is demo step 4.

- immudb, named in the brief, is under the Business Source License 1.1 from tag `v1.9DOM.2` (December 2023) onwards. BSL is not OSI-approved, so it fails rule 5 of the brief.
- Trillian is Apache-2.0 and is the verifiable Merkle log behind Certificate Transparency, which gives a strong, well-known story for the "immutable ledger" requirement.
- Trillian supports PostgreSQL storage (`storage/postgresql` in v1.8.0), so it can reuse the core PostgreSQL instance with its own database instead of adding MySQL. This is validated in Phase 1.
- **Risk:** the Trillian README states the project is in maintenance mode and recommends [Tessera](https://github.com/transparency-dev/tessera) for new logs. Releases continue (v1.8.0 in September 2026), which is enough for this project's lifetime. If Trillian blocks us, Tessera (Apache-2.0, v1.0.4) is the planned fallback. Tessera is a Go library, so it would mean writing a small log service ourselves.
- The event name `ledger.sealed` and the seal-verification test in the brief stay unchanged. Only the backing technology changes.

## Alternatives considered

| Concern | Option | Why not chosen |
|---|---|---|
| Event bus | Apache Kafka 4.3.1 (KRaft) | Apache-2.0 and widely known, but far heavier on a laptop. Its partition model adds operational work we do not need at this scale |
| Event bus | Redpanda | Business Source License 1.1, not OSI-approved |
| Object storage | Garage v2.4.1 | AGPL-3.0 (allowed) and lightweight, but its S3 API coverage is narrower and copyleft adds review overhead. Kept as the fallback |
| Object storage | MinIO | Repository archived |
| Ledger | immudb 1.11.2 (current) | Business Source License 1.1 |
| Ledger | immudb `v1.9DOM.1` (last Apache-2.0 release) | Licensed correctly, but from November 2023 with no security fixes since. Hard to defend in front of a jury |
| Ledger | Hash chain and Merkle root in PostgreSQL, verified by our own code | Lightest option, but it is "trust our code" rather than an independent, standard verifiable log |
| Ledger | Tessera v1.0.4 | Actively developed successor to Trillian, but it is a library, not a ready-to-run server. Kept as the fallback |
| Secrets | HashiCorp Vault | Business Source License 1.1. OpenBao is the open-source fork |
| Background jobs | n8n | Sustainable Use License, not OSI-approved |

## Consequences

- Every component is under an OSI-approved license. The register in [docs/licenses.md](../licenses.md) must stay in sync with the Compose files from Phase 1 onwards.
- The brief mentions immudb in section 2.1 and in demo step 4. Where this ADR differs from the brief, this ADR applies. The team may also update the brief.
- NATS keeps the `core` profile light. If a jury member expects Kafka, the answer is the resource budget and the CloudEvents binding: events stay portable to Kafka later.
- Trillian adds two containers (log server and log signer) to the `core` profile. Its maintenance-mode status is a known, accepted risk with a named fallback.
- The Coraza WAF is a stretch goal. Its proxy-wasm build was last released in July 2025, and APISIX has no built-in Coraza plugin, so it would run through APISIX's Wasm support. Feasibility is checked in Phase 1.

## Open items

These need a team decision. They are not decided by this ADR.

1. **Context broker (Orion-LD needs MongoDB).** Orion-LD 1.12.0 is AGPL-3.0, but it requires MongoDB 4.2 or later, and every such release is under the SSPL, which is not OSI-approved. Options:
   - Replace Orion-LD with **Stellio** (Apache-2.0, PostgreSQL-backed NGSI-LD broker).
   - Replace it with **Scorpio** (BSD-3-Clause, PostgreSQL-backed NGSI-LD broker).
   - Keep Orion-LD on **FerretDB** (Apache-2.0) with the DocumentDB extension (MIT) as a MongoDB-compatible backend. Compatibility is unverified.

   It is not needed before Phase 5 (meter reconciliation), but should be settled in its own ADR before then.
2. **Tenant model in Keycloak** (realm per tenant or Organizations): Phase 2 ADR, as required by the brief.
3. **Tenant isolation on the event bus** (subject prefix or header): Phase 2 ADR.
