# ADR-0005: Request and complete workflows through events; one workflow capability talks to Flowable

- **Status:** Proposed (becomes Accepted when the pull request is merged)
- **Date:** 2026-10-22
- **Deciders:** EcoTrace team
- **Issue:** #36

## Context

Approvals must follow each tenant's own BPMN process from its config pack, and Company A and B must differ without code changes (brief, Phase 4). Several apps need approvals: Carbon Ledger (activity data) and Purchase Approval (purchase invoices), with more to come. ADR-0001 chose Flowable 8.0.0.

## Decision

1. **Process definitions live in the tenant pack** (`tenants/<id>/workflows/<process-key>.bpmn`). `dxctl tenant create` deploys them to Flowable under the Flowable tenant id equal to the EcoTrace tenant id. Unchanged files are skipped by content hash.
2. **Only the workflow capability (`capabilities/workflow-ui`) talks to Flowable.**
   - Apps publish `workflow.requested` with a process key, a business key, a title and variables.
   - The capability starts the tenant's process, once per business key.
   - Users complete tasks through `/workflow/tasks`, which only lists tasks of their tenant whose candidate group is one of their roles.
   - When a process ends, `workflow.completed` is published with the outcome and every decision (step, person, comment, time).
3. **Apps react to `workflow.completed`.** Carbon Ledger turns an approved `verify-activity` into an emission entry. Purchase Approval records its decision. Direct approval endpoints are refused when the tenant has a process.
4. **Roles are the candidate groups.** `uploader`, `reviewer`, `approver` and `tenant-admin` come from `org.yaml`, so the BPMN files can name roles without knowing users.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Each app calls Flowable REST directly | Every app would need Flowable credentials and its own task inbox, and would be coupled to the engine's API |
| Flowable service tasks calling back into the apps over HTTP | The BPMN files would contain service URLs, so tenant packs would depend on deployment details |
| Approval states hard-coded in each app | Company A and B could not have different flows without code changes |

## Consequences

- Swapping the BPMN engine affects one capability, not every app.
- Workflow requests and outcomes are visible on the event bus (`make events`) and replayable.
- Decisions are stored in the process (`decisions` variable) and in the consuming app, so the lineage shows who approved at each step.
- If Flowable is down, requests wait on the bus and are retried. Tasks cannot be completed until it is back.
