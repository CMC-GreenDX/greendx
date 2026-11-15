# EcoTrace

[![lint](https://github.com/CMC-GreenDX/greendx/actions/workflows/lint.yml/badge.svg)](https://github.com/CMC-GreenDX/greendx/actions/workflows/lint.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

EcoTrace is an open-source DX-OS platform for Vietnamese enterprises. It turns incoming documents (electricity bills, fuel slips, purchase invoices) into reviewed and approved data, then into Scope 1 and 2 greenhouse-gas figures that trace back to the original document and are sealed in a tamper-evident log. One core serves many companies; a company is added by configuration, without code changes.

Built by team CMC-GreenDX (CMC University) for OLP Phần mềm nguồn mở 2026, topic "DX-OS Open-Core".

## Why

- **GHG inventory and CBAM.** Decision 42/2026/QĐ-TTg requires 2,441 facilities to run GHG inventories, and EU CBAM requires verified emissions data from exporters.
- **Manual document intake.** Bills and slips arrive by email, chat or paper and are retyped into spreadsheets, so the figures lose their link to the source.

## Architecture

```text
Tier 3  Apps            carbon-ledger, purchase-approval        (enabled per company)
Tier 2  Capabilities    document-intake, workflow, dashboard     (only call the core through the gateway and events)
Tier 1  Headless core   Keycloak, APISIX, PostgreSQL + RLS, Hasura, ClamAV, SeaweedFS,
                        NATS JetStream, Flowable, Trillian
```

Component choices and their reasons are in the [ADRs](docs/adr); versions and licenses are in [docs/licenses.md](docs/licenses.md).

## Status

| Works today | Planned before v1.0.0 |
|---|---|
| Core services in Docker Compose; three companies onboarded from config packs with `dxctl`; tenant isolation with row-level security | Secrets in OpenBao, background jobs in Kestra, monitoring |
| Document Intake: malware scan, e-invoice XML, AI extraction with a rule-based fallback, review and duplicate check | Meter reconciliation (`simulators/meter-sim`) |
| BPMN approvals per company; Carbon Ledger with lineage; period close sealed in Trillian; Excel and CSV export; live dashboard | Cold storage for closed periods; Kubernetes deployment (`deploy/k8s`) |

## Repository layout

| Path | Contents |
|---|---|
| `core/` | Gateway routes, database setup, JSON Schemas for config packs |
| `capabilities/` | Document Intake, workflow service, demo console |
| `apps/` | Carbon Ledger, ledger sealer, Purchase Approval |
| `tenants/` | One config pack per company |
| `tools/` | `dxctl` onboarding CLI, API docs build, sample data |
| `deploy/compose/` | Docker Compose setup |
| `docs/` | Install guide, ADRs, licenses, API guide, design guide |

## Getting started

You need Linux (or WSL 2) with about 16 GB RAM, Docker Engine with Compose, `git`, `make`, `curl` and `jq`.

```sh
git clone https://github.com/CMC-GreenDX/greendx.git && cd greendx
cp .env.example .env   # then replace the change-me-… secrets
make up                # build and start (first run: 10 to 20 minutes)
make health            # every service must say OK
```

Open <http://localhost:9080> and log in as `alice` with the `DEMO_USER_PASSWORD` from `.env`. The [install guide](docs/install.md) covers configuration, checks, running without `make` and troubleshooting; the [demo script](docs/demo-script.md) walks through the product.

## API

The reference at <http://localhost:9080/api-docs> lets you log in and try each endpoint. It is also published at <https://cmc-greendx.github.io/greendx/api/>. The [API guide](docs/api/README.md) covers tokens, examples, errors, events and a Postman collection.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Bugs and ideas go to [GitHub Issues](https://github.com/CMC-GreenDX/greendx/issues). Changes are listed in the [changelog](CHANGELOG.md), and the self-assessment against the competition's "Points of Fail" is in [docs/pof-checklist.md](docs/pof-checklist.md).

## License

EcoTrace is licensed under the [Apache License 2.0](LICENSE): anyone may use, study, change and redistribute it, including commercially, as long as they keep the license and the [NOTICE](NOTICE). Every source file carries an SPDX header, checked by `make license-check` and CI.

Third-party components keep their own licenses, listed in [docs/licenses.md](docs/licenses.md). They are pulled from their official registries at pinned versions; none of their source is copied into this repository.
