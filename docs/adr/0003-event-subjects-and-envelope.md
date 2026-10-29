# ADR-0003: Use tenant-prefixed NATS subjects and CloudEvents envelopes

- **Status:** Proposed (becomes Accepted when the pull request is merged)
- **Date:** 2026-10-22
- **Deciders:** EcoTrace team
- **Issue:** #25

## Context

[ADR-0001](0001-core-technology-choices.md) chose NATS JetStream for domain events and left open how tenants are separated on the bus: a subject prefix or a header (brief section 3.2). Document Intake now publishes its first events, and Carbon Ledger and Purchase Approval will consume them in Phases 4–5.

## Decision

1. **Subjects:** `tenant.<tenant_id>.<event type>`, for example `tenant.company-a-steel.document.extracted`.
2. **Envelope:** CloudEvents 1.0 in structured JSON mode (`Content-Type: application/cloudevents+json`), with:
   - `type`: `vn.ecotrace.<event type>.v1`, versioned so the schema can change without breaking consumers;
   - `source`: the publishing capability, for example `/capabilities/document-intake`;
   - `subject`: the business object's id (the document id);
   - extension attributes `tenantid` and `traceid`.
3. **Stream:** one JetStream stream `ECOTRACE_EVENTS` captures `tenant.*.>` (file storage, 30 days). The CloudEvent `id` is also the `Nats-Msg-Id`, so a retried publish is not stored twice.
4. **Events so far:** `document.received` (after the malware scan and storage) and `document.extracted` (after classification and extraction, with the fields). Brief section 4 also names `document.classified`; it is folded into `document.extracted` because both happen in one step.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Tenant only in a header or in the payload | Consumers and permissions cannot filter on headers; every consumer would receive every tenant's events |
| One stream per tenant | Strongest separation, but onboarding a tenant would create streams; reconsider together with per-tenant NATS accounts in Phase 2 |
| Binary CloudEvents mode (attributes in NATS headers) | Works, but the structured mode keeps each message self-describing and easy to inspect (`make events`) |

## Consequences

- A consumer subscribes to `tenant.*.document.extracted` (all tenants) or `tenant.<id>.document.extracted` (one tenant). NATS permissions per tenant can later be expressed on the prefix.
- The tenant appears twice (subject and `tenantid`). Consumers must check that they agree.
- Events are published after the database commit, without an outbox. If NATS is down, the upload still succeeds and the pipeline shows a warning, but the event is lost. A transactional outbox is a follow-up before consumers depend on every event.
