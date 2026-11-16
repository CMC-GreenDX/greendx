# Project brief

EcoTrace is the entry of team CMC-GreenDX (CMC University) to OLP Phần mềm nguồn mở 2026, topic "DX-OS Open-Core": build an open-source operating system for the digital enterprise, whose core can move from one company to another without code changes.

This brief states the problem, the scope and the architecture. Technology choices and their reasons are in the [ADRs](adr); the current state is in the [README](../README.md#status).

## Problem

Vietnamese enterprises still run many cross-department tasks with Excel, chat and paper. The project addresses two needs:

- **Emissions evidence.** Inventory teams need quantities, emission-factor versions, approvals and original documents that an independent reviewer can trace and check.
- **Manual document intake.** Electricity bills, fuel slips and purchase invoices are retyped into spreadsheets, and the figures can no longer be traced to the source document.

EcoTrace focuses on a small deployment that a company can run on its own infrastructure, with source code and configuration available for review.

## Scope

In scope:

- A headless core that any company and any application can use.
- Document Intake: scan, store, classify and extract documents, with a person reviewing uncertain fields.
- Carbon Ledger: Scope 1 (fuel) and Scope 2 (purchased electricity) emissions with lineage to the source document, period close, a tamper-evident seal, and an inventory export.
- Purchase Approval: a second, small app on the same intake and workflow, to show that the core is reusable beyond carbon.
- Onboarding a company from a config pack, in minutes.

Out of scope: Scope 3, carbon credit trading, and official certification. EcoTrace prepares evidence for an independent verifier; it does not certify.

## Architecture

| Tier | Contents | Rule |
|---|---|---|
| 3. Apps | Carbon Ledger, Purchase Approval | Enabled or disabled per company in `tenant.yaml` |
| 2. Capabilities | Document Intake, workflow and task inbox, dashboard, user console | Call the core only through the API gateway and the event bus |
| 1. Headless core | Identity, gateway, file scanning, structured data and its API, object storage, workflow engine, event bus, tamper-evident log | No user interface and no company-specific logic |

The deployed core uses Keycloak, Apache APISIX, PostgreSQL with row-level security, Hasura, ClamAV, SeaweedFS, NATS JetStream, Flowable and Trillian. [ADR-0001](adr/0001-core-technology-choices.md) records the choices; [the Compose service list](../deploy/compose/README.md) identifies what is implemented. OpenBao, Kestra, monitoring, meter reconciliation and Kubernetes remain planned work, as the [README status table](../README.md#status) records. Document Intake uses a hosted LLM with a rule-based fallback ([ADR-0002](adr/0002-hosted-llm-api-for-document-intake.md)).

## Multi-tenancy

A tenant is one company, described by a config pack in `tenants/<id>/`:

| File | Defines |
|---|---|
| `tenant.yaml` | Name, locale, enabled apps (`modules`) |
| `org.yaml` | Departments, roles, users |
| `document-types.yaml` | Accepted document types and their extraction schema |
| `workflows/*.bpmn` | Approval processes |
| `emission-sources.yaml` | Facilities and emission sources |
| `emission-factors.yaml` | Emission factors, with their sources |

Config packs are validated against the JSON Schemas in `core/schemas/` and applied with `dxctl tenant create`. All companies share the `ecotrace` Keycloak realm, with a tenant group and a `tenant_id` token claim per company. Service database roles enforce row-level security on tenant tables; Hasura applies its own tenant permissions. Each company gets its own users and roles, its own storage bucket, its own event subjects ([ADR-0003](adr/0003-event-subjects-and-envelope.md)) and its own log in Trillian. The tenant model is in [ADR-0004](adr/0004-tenant-model.md).

## Requirements

- Every component has an OSI-approved license and a pinned version ([docs/licenses.md](licenses.md)).
- The `core` Compose profile runs on a 16 GB laptop.
- Every emission figure links to its source document, its reviewer, its approver, the factor version used and its seal.
- Tenant isolation, emission calculation, seal verification and the event contracts have automated tests.
- No secrets in Git; only `.env.example` is committed.
- User-facing text is in Vietnamese and English through i18n files.

## Demo

1. An accountant at Company A uploads an electricity bill. It is scanned, read, and reviewed where confidence is low.
2. The department head approves it in the task inbox; the dashboard updates and every figure opens its lineage.
3. The period is closed and sealed. A row changed directly in the database is detected by the seal check.
4. Company C is onboarded with `dxctl tenant create`, logs in, and follows its own approval flow.
5. A purchase invoice goes to Purchase Approval instead of the Carbon Ledger.
