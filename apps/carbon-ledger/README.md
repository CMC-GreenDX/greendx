# carbon-ledger

Carbon Ledger (Tier 3 app, FastAPI). It turns reviewed documents into approved Scope 1 and 2 emissions, with full lineage back to the source document. It is enabled per tenant with `modules.carbon-ledger` in `tenant.yaml`.

## Flow

1. Subscribes to `tenant.*.document.>` on NATS JetStream with a durable consumer ([ADR-0003](../../docs/adr/0003-event-subjects-and-envelope.md)). Each event is acknowledged after the database commit.
   - `document.extracted` with status `extracted` (every field above the threshold) and `document.reviewed` are used.
   - Documents that need review wait until a person reviews them.
2. Matches the document to a source in the tenant's `emission-sources.yaml` (document type plus optional `match` on fields), takes the quantity field and the period, and creates an **activity record** (`pending_approval`).
   - Documents that match no source, such as purchase invoices, create nothing.
3. A user with the **approver** role approves or rejects. Approval creates an **emission entry**: `co2e_kg = quantity × factor`. The factor comes from `emission-factors.yaml`, and the entry stores the factor key, value, unit, version, citation and status, so later factor changes never rewrite past results.
4. `GET /ledger/entries/{id}/lineage` returns the chain: entry → activity → approval → document (file, extractor, SHA-256) → extracted fields → human corrections → factor → period.

Tables live in the `ledger` schema with row-level security. The service connects as `ledger_app` ([ADR-0004](../../docs/adr/0004-tenant-model.md)).

## API (through the gateway, bearer token required)

| Method and path | Purpose |
|---|---|
| `GET /ledger/activities` | Activities of the tenant, plus whether the caller can approve |
| `POST /ledger/activities/{id}/approve` | Approver only. Computes and records the emission entry |
| `POST /ledger/activities/{id}/reject` | Approver only. Body `{"reason": "..."}` |
| `GET /ledger/summary?period=YYYY-MM` | Scope 1 and 2 totals, totals per source, entries and periods |
| `GET /ledger/entries/{id}/lineage` | Where a figure comes from |

Not yet: approval through a BPMN workflow, period close with a Trillian seal, and meter reconciliation.

Test: `make ledger-check`.
