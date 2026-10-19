# Project Brief — DX-OS Open-Core: EcoTrace

> Working product name: **EcoTrace** (the team may rename it).
> Competition: OLP Phần mềm nguồn mở 2026 — topic "DX-OS Open-Core".
> Team: 3 students. Submission deadline: verify with the organisers (the official brief says "Sunday 06/12", most likely 06/12/2026).
> This file is the single source of truth for Claude Code. Read it fully before doing anything.

---

## 0. How to work (rules for Claude Code)

1. **Work phase by phase** (Section 9). At the end of each phase: stop, summarise what was built, list open questions, and wait for the team's review. Never start the next phase on your own.
2. **Every change goes through an issue → branch → PR.** Never push directly to `main`. Follow the conventions in Section 8 exactly.
3. **English only** for code, identifiers, branch names, commits, issues, PRs, README and docs. Do not mix Vietnamese and English. (User-facing UI text may be localised to Vietnamese through i18n files, never hard-coded.)
4. **Explain decisions.** For every significant architectural choice, write a short ADR in `docs/adr/NNNN-title.md` (context, decision, alternatives, consequences). The team must be able to defend every choice in front of the jury.
5. **Licenses matter.** Only use components with an OSI-approved license. Before adding any dependency or container image, check its current license and record it in `docs/licenses.md` (component, version, license, how it is used). Flag anything uncertain instead of guessing.
6. **Pin versions.** Every container image and package uses an exact version. Verify the version exists before using it.
7. **Keep it runnable on a student laptop** (16 GB RAM). Use Docker Compose profiles so that the core can run without the heavy optional services.
8. **No business logic in the core.** If you are about to write something company-specific in `core/`, stop: it belongs in `capabilities/`, `apps/`, or a tenant config pack.

---

## 1. Problem statement

Vietnamese enterprises still perform many cross-department tasks by hand (Excel, Zalo, paper). Two needs became urgent in 2026:

- **Greenhouse-gas (GHG) inventory and CBAM.** Decision 42/2026/QĐ-TTg (effective 25/09/2026) lists 2,441 facilities that must run GHG inventories under Decree 06/2022 (amended by 119/2025 and 83/2026). EU CBAM entered its definitive period in 2026: importers file the first annual declaration for 2026 imports by 30/09/2027, and actual emissions must be verified by an independent party — so Vietnamese exporters must deliver emissions data that is traceable to evidence.
- **Manual document intake.** Electricity bills, fuel slips, warehouse issue slips and purchase invoices arrive by email, chat or paper, are retyped into spreadsheets, and their figures cannot be traced back to the source document.

Existing tools (Persefoni, IBM Envizi, SAP, local proprietary SaaS) are expensive, closed, and do not run on-premise for SMEs.

**EcoTrace** is a DX-OS Open-Core platform where:
- a **headless core** (Tier 1) provides identity, API gateway, structured/unstructured data, workflow, events and an immutable ledger to any application, for any company;
- a reusable **Document Intake** capability (Tier 2, Intelligence space) turns incoming documents into structured, classified data;
- a **Carbon Ledger** business app (Tier 3) turns approved data into Scope 1 & 2 emissions with full lineage back to the source document and a sealed, tamper-evident record.

The core is worth **50% of the grade** and must be **portable from Company A to Company B without code changes**.

---

## 2. Architecture (3 tiers, separation of concerns)

```
Tier 3 – Business apps      apps/carbon-ledger         (plug-in, can be disabled per tenant)
                            apps/purchase-approval     (tiny second consumer, proves reuse)
                                   ▲ subscribe to domain events
Tier 2 – Capability spaces  capabilities/document-intake   [I] OCR + LLM classify/extract
                            capabilities/portal             [H] single web portal (Nuxt 3)
                            capabilities/workflow-ui        [P] "My approvals" task inbox
                            capabilities/dashboard          [D] real-time + historical analytics
                                   ▲ only via API Gateway / event bus
Tier 1 – Headless core      core/  (NO end-user UI)
```

**One web for the user, separate services behind it.** The user logs in once (SSO) to the portal and sees modules according to role and tenant. Each module is its own service/container that talks to others only through the API gateway and the event bus.

### 2.1 Tier 1 core services (mandatory: Identity/SSO, API Gateway, structured + unstructured data, Workflow)

| Concern | Component (verify license & version) | Notes |
|---|---|---|
| Identity, SSO, MFA | Keycloak | OIDC; tenant claim in JWT |
| API Gateway, zero-trust edge | Apache APISIX (+ Coraza WAF plugin if feasible) | JWT validation, rate limiting, routing |
| Secrets | **OpenBao** (MPL-2.0 fork of Vault) | HashiCorp Vault is BSL → do not use |
| File quarantine | ClamAV | every upload scanned before storage |
| Structured data (OLTP) | PostgreSQL (+PostGIS optional) | row-level security by `tenant_id` |
| Auto-generated API | Hasura GraphQL Engine v2 (Apache-2.0) | permissions use tenant claim |
| Object storage | **SeaweedFS** or Garage (S3-compatible) | MinIO community edition is in maintenance mode — verify before choosing; write an ADR |
| Workflow (BPMN) | Flowable (Apache-2.0) | BPMN files come from tenant config packs |
| Background jobs | Kestra (Apache-2.0) | n8n is not OSI-licensed → do not use |
| Event bus | **Apache Kafka (KRaft)** or NATS JetStream | Redpanda is BSL → do not use; events in CloudEvents format |
| Immutable ledger | immudb | seals approved emission records |
| Context broker (IT/OT) | FIWARE Orion-LD (NGSI-LD) | meters/sensors as digital-twin entities |
| Logs, metrics | Vector + Prometheus + Grafana | audit log of every core call |
| Backup | Velero (k8s phase) / pg_dump + bucket sync (compose phase) | |

Optional / heavy (Compose profile `full`): Trino + Apache Iceberg (cold data lakehouse), OpenMetadata (lineage catalogue), Metabase or Cube.dev, Ollama (local LLM), Qdrant/Meilisearch.

### 2.2 Design principles from the competition brief (must be visible in the demo)

1. **Data lifecycle separation** — hot transactional data in PostgreSQL; closed reporting periods are exported to Iceberg (or Parquet on S3 in the minimal profile) for analytics without loading the OLTP core.
2. **IT/OT convergence** — simulated electricity meters / fuel flow sensors push readings into Orion-LD; the Carbon Ledger reconciles meter readings with billed amounts from documents.
3. **Next-gen data governance** — every emission figure has lineage: `emission_entry → extraction_field → source_document → approval_task → seal`. Expose it in the UI ("click a number, see the original document").
4. **Zero-trust + GitOps** — JWT checked at the gateway for every call, malware scan at the edge, secrets from OpenBao, infrastructure declared as code; in the k8s phase, ArgoCD reconciles from Git.

---

## 3. Multi-tenancy and portability (the most important part)

A **tenant** = one company. Onboarding a new company must be done by **configuration only**.

### 3.1 Tenant config pack

```
tenants/
  company-a-steel/
    tenant.yaml            # id, name, locale, enabled modules, branding
    org.yaml               # departments, roles, users (seed)
    document-types.yaml    # which document types intake accepts + extraction schema
    workflows/*.bpmn       # approval processes
    emission-sources.yaml  # sources, activity units, scope, factor reference
    emission-factors.yaml  # factor values + source citation
    seed/                  # sample documents and meter data for the demo
  company-b-logistics/
    ...
```

Rules:
- `core/` and `capabilities/` never reference a specific tenant.
- Enabling/disabling a Tier 3 app is a flag in `tenant.yaml`.
- Schemas for document types and emission sources are validated with JSON Schema (`core/schemas/`).

### 3.2 Isolation

- Keycloak: one realm per tenant (or Organizations feature — write an ADR), `tenant_id` claim in tokens.
- PostgreSQL: `tenant_id` column + RLS policies on every business table.
- Object storage: one bucket per tenant.
- Event bus: topics prefixed by tenant or tenant in event header (ADR).
- OpenBao: secrets path per tenant.

### 3.3 `dxctl` CLI (Python or Go)

```
dxctl tenant validate tenants/company-b-logistics
dxctl tenant create   tenants/company-b-logistics   # realm, roles, users, RLS rows, bucket, BPMN deploy, seeds
dxctl tenant disable  company-b-logistics
dxctl tenant list
```

**Acceptance demo:** a fresh company is onboarded in under 5 minutes, users log in, upload a document and see it flow through — with zero code changes.

---

## 4. Capability: Document Intake [I] (generic, knows nothing about carbon)

Flow:
1. Upload via portal or API (also an email-ingest endpoint as stretch goal).
2. ClamAV scan → reject or store in tenant bucket. Emit `document.received`.
3. OCR (Vietnamese-capable, e.g. PaddleOCR or Tesseract `vie`; also parse e-invoice XML directly when available).
4. Classify document type using the tenant's `document-types.yaml` (LLM via Ollama with a small model, with rule-based fallback so the demo works without GPU).
5. Extract fields per schema, with confidence score per field. Emit `document.classified` and `document.extracted`.
6. Low-confidence fields → human review task in the workflow inbox.

Demo document types (keep to these 4): electricity bill, fuel slip, warehouse issue slip, purchase invoice.

Intake publishes events; it never calls Carbon Ledger directly.

---

## 5. App: Carbon Ledger (Tier 3)

- Subscribes to `document.extracted` for document types mapped to emission sources.
- Creates a draft `activity_record` (quantity, unit, period, facility, source) linked to the document and extracted fields.
- Starts the tenant's BPMN "verify activity data" process (e.g. department head approves).
- On approval: computes `emission_entry` = activity × factor (Scope 1 fuel, Scope 2 electricity only), stores factor version used.
- Period close: locks the period, writes a hash of all entries to immudb (`ledger.sealed`), exports to cold storage.
- Reconciliation: compares meter readings from Orion-LD with billed kWh; flags deviations above a tenant-configured threshold.
- Reports: period summary by scope/facility/source; export CSV/XLSX in a simple inventory template; every figure links to its lineage.

Out of scope: Scope 3, carbon credit trading, official certification.

## 6. Second consumer: Purchase Approval (tiny)

Subscribes to `document.extracted` for `purchase_invoice`, starts a simple BPMN approval. Purpose: prove the intake capability and core are reusable beyond carbon. Keep it minimal.

## 7. Portal [H] and dashboards [D]

- Nuxt 3 + Vue 3 + Tailwind; OIDC login via Keycloak; module menu driven by tenant config and role.
- Screens: Document inbox, Document detail (preview + extracted fields + lineage), My approvals, Carbon dashboard (real-time via WebSocket — Centrifugo or SSE), Period close & seal verification, Tenant admin (read-only view of config).
- All UI strings through i18n (`vi`, `en`).

---

## 8. Team conventions (must be documented in `CONTRIBUTING.md`)

- **Branch:** `<type>/<issue-number>-<short-kebab-desc>` e.g. `feat/12-tenant-onboarding-cli`
- **Commit:** Conventional Commits `<type>(<scope>): <imperative summary>` e.g. `feat(intake): add electricity bill extractor`
  - types: `feat, fix, docs, refactor, test, chore, ci, build, perf`
  - scopes: `core, gateway, identity, data, storage, workflow, events, ledger, intake, carbon, purchase, portal, dashboard, dxctl, infra, docs`
- **Issue title:** `[<Area>] <Imperative summary>` e.g. `[Core] Add RLS policies for tenant isolation`, using templates in `.github/ISSUE_TEMPLATE/` (Context, Scope, Acceptance criteria).
- **PR:** title follows commit format; body has Summary, How to test, `Closes #N`; at least one teammate approval; squash merge.
- **Versioning:** SemVer tags `v0.x.y`; `CHANGELOG.md` generated from commits.
- `CONTRIBUTING.md` must also state **why** these conventions exist: traceable history (issue → branch → commit → PR), automatic changelog, easier review, easier outside contribution.

## 9. Repository layout

```
.
├── core/                    # Tier 1: compose/k8s manifests + config for core services, schemas, gateway routes
├── capabilities/
│   ├── document-intake/     # service (Python FastAPI)
│   ├── portal/              # Nuxt 3
│   └── dashboard/
├── apps/
│   ├── carbon-ledger/       # service
│   └── purchase-approval/
├── tenants/                 # config packs (company-a-steel, company-b-logistics)
├── tools/dxctl/
├── simulators/meter-sim/    # fake IoT meters → Orion-LD
├── deploy/
│   ├── compose/             # docker-compose.yml with profiles: core, app, full
│   └── k8s/                 # Helm/Kustomize + ArgoCD apps (later phase)
├── docs/ (architecture.md, adr/, licenses.md, demo-script.md, api/)
├── .github/ (ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md, workflows/)
├── LICENSE (Apache-2.0), README.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, CHANGELOG.md, Makefile
```

## 10. Phases (stop and wait for review after each)

| Phase | Goal | Done when |
|---|---|---|
| 0 Bootstrap | Repo skeleton, LICENSE, README draft, CONTRIBUTING, templates, CI lint, `docs/licenses.md` with verified licenses, ADR-0001 tech choices | Team approves conventions and stack |
| 1 Core up | Compose profile `core`: Keycloak, APISIX, Postgres+Hasura, object storage, ClamAV, OpenBao, Kafka/NATS, Flowable, immudb, observability | `make up` + `make health` green; a sample API call goes Gateway → Hasura with JWT |
| 2 Tenancy | Config pack schemas, `dxctl`, RLS, per-tenant realm/bucket/secrets | Two tenants created from config; cross-tenant read is denied (automated test) |
| 3 Intake | Upload → scan → OCR → classify → extract → events; review task for low confidence | 4 sample documents per tenant processed end-to-end |
| 4 Workflow | BPMN deployment from config packs; task inbox API | Different approval flows for A and B with no code change |
| 5 Carbon Ledger | Activity records, approval, emission calculation, lineage, period close + immudb seal, meter reconciliation | Seal verification detects a tampered row |
| 6 Portal & dashboard | SSO portal, modules per tenant, lineage view, real-time dashboard | Full demo flow in Section 11 works in browser |
| 7 Data lifecycle | Closed periods exported to cold storage; analytical query (Trino/DuckDB) | Historical report runs without touching OLTP |
| 8 GitOps & resilience | k3d/kind + ArgoCD, backup/restore script | Delete a service → ArgoCD restores it; restore from backup works |
| 9 Polish | README install guide, architecture diagram, demo seed, demo script, release `v1.0.0` | A stranger can clone, run and follow the demo |

## 11. Demo script (target)

1. Company A (steel) accountant uploads an electricity bill PDF → malware scan → OCR/LLM extracts kWh → warehouse head approves in "My approvals".
2. Dashboard updates in real time (Scope 2); click the figure → original bill + approval + seal.
3. Meter simulator shows a deviation vs billed kWh → flagged.
4. Close the period → seal in immudb → tamper one DB row → verification fails.
5. `dxctl tenant create tenants/company-b-logistics` → Company B logs in; a fuel slip goes to Scope 1 via a different approval flow.
6. Upload a purchase invoice → routed to Purchase Approval, not Carbon Ledger — proving the core and intake are reusable.

## 12. Quality bar

- Automated tests for tenant isolation, emission calculation, seal verification, event contracts.
- OpenAPI/GraphQL schema published in `docs/api/`.
- No secrets in Git; `.env.example` only.
- Every service has a healthcheck and structured JSON logs with `tenant_id` and `trace_id`.
