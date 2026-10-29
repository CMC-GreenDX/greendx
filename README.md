# EcoTrace

[![lint](https://github.com/CMC-GreenDX/greendx/actions/workflows/lint.yml/badge.svg)](https://github.com/CMC-GreenDX/greendx/actions/workflows/lint.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Status: Phase 1 in progress.** The identity, gateway and data slice of the core runs with Docker Compose. This README is a draft and is completed in Phase 9.

EcoTrace is a DX-OS Open-Core platform for Vietnamese enterprises. A reusable, headless core lets any company turn incoming documents (electricity bills, fuel slips, warehouse issue slips, purchase invoices) into structured, approved data, and then into Scope 1 and 2 greenhouse-gas figures that can be traced back to the original document and verified against a tamper-evident ledger.

It is built for the OLP Phần mềm nguồn mở 2026 competition, topic "DX-OS Open-Core".

## Why

- **GHG inventory and CBAM.** Decision 42/2026/QĐ-TTg requires 2,441 facilities to run GHG inventories, and EU CBAM requires verified emissions data from exporters. That data must be traceable to evidence.
- **Manual document intake.** Bills and slips arrive by email, chat or paper, are retyped into spreadsheets, and the figures can no longer be traced to their source.
- **Existing tools** are expensive, closed and do not run on-premise for SMEs.

## Architecture

```text
Tier 3  Business apps        apps/carbon-ledger, apps/purchase-approval
           ▲ subscribe to domain events
Tier 2  Capability spaces    document-intake [I], portal [H], workflow-ui [P], dashboard [D]
           ▲ only via API gateway / event bus
Tier 1  Headless core        identity, gateway, secrets, data, storage, workflow, events, ledger
```

- **Tier 1, headless core:** no end-user UI and no business logic. It is portable from one company to another without code changes.
- **Tier 2, capabilities:** reusable services such as Document Intake, which knows nothing about carbon.
- **Tier 3, apps:** plug-ins that can be enabled per tenant, such as the Carbon Ledger.

A tenant (one company) is onboarded by configuration only, from a config pack in `tenants/`.

The component choices and their reasons are recorded in [ADR-0001](docs/adr/0001-core-technology-choices.md). Licenses and pinned versions are listed in [docs/licenses.md](docs/licenses.md).

## Repository layout

| Path | Contents |
|---|---|
| `core/` | Tier 1: manifests and configuration for core services, JSON Schemas, gateway routes |
| `capabilities/` | Tier 2: document intake, portal, workflow UI, dashboard |
| `apps/` | Tier 3: carbon ledger, purchase approval |
| `tenants/` | Tenant config packs |
| `tools/dxctl/` | Tenant onboarding CLI |
| `simulators/meter-sim/` | Simulated IoT meters |
| `deploy/` | Docker Compose (profiles `core`, `app`, `full`) and Kubernetes manifests |
| `docs/` | Project brief, architecture, ADRs, licenses, API schemas |

## Roadmap

| Phase | Goal |
|---|---|
| 0 | Bootstrap: repository, conventions, CI lint, license register, ADR-0001 |
| 1 | Core services running with Docker Compose |
| 2 | Multi-tenancy: config packs, `dxctl`, row-level security |
| 3 | Document Intake |
| 4 | Workflow and task inbox |
| 5 | Carbon Ledger |
| 6 | Portal and dashboards |
| 7 | Data lifecycle (cold storage, analytics) |
| 8 | GitOps and resilience |
| 9 | Polish and release `v1.0.0` |

The full plan is in [docs/project-brief.md](docs/project-brief.md).

## Getting started

The core needs a machine with about 16 GB RAM and Docker. The easiest way is a GitHub codespace: the repository's dev container selects a 4-core / 16 GB machine with Docker installed.

```sh
make up       # start PostgreSQL, Keycloak, Hasura and APISIX
make health   # check every service
make demo     # identity -> gateway -> data, with tenant isolation
```

See [docs/demo-script.md](docs/demo-script.md) for the walkthrough and [deploy/compose](deploy/compose) for details. Full installation instructions are completed in Phase 9.

## API

Every feature of the console is available through the APIs behind the gateway. The reference page at <http://localhost:9080/api-docs> lets you log in and try each endpoint. The [API guide](docs/api/README.md) covers tokens, curl examples, errors, events and a Postman collection.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request. All participants follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

EcoTrace is licensed under the [Apache License 2.0](LICENSE). Third-party components keep their own licenses, listed in [docs/licenses.md](docs/licenses.md).
