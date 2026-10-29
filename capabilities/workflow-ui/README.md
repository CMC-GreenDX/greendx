# workflow-ui

Workflow capability [P]: runs each tenant's BPMN processes on Flowable and serves the "My approvals" inbox ([ADR-0005](../../docs/adr/0005-workflow-through-events.md)). It is the only service that talks to Flowable.

| Interface | Purpose |
|---|---|
| Event `tenant.<id>.workflow.requested` | An app asks for a process (`process_key`, `business_key`, `title`, `variables`). It is started once per business key |
| `GET /workflow/tasks` | Open tasks of the caller's tenant whose candidate group is one of the caller's roles |
| `POST /workflow/tasks/{id}/complete` | `{"approved": true, "comment": "..."}`. Checks tenant and role, records the decision, and publishes `workflow.completed` when the process ends |

Process definitions come from `tenants/<id>/workflows/*.bpmn` and are deployed by `dxctl tenant create`. Company A approves activity data in one step, Company B in two steps (reviewer, then approver), with the same code. Test: `make workflow-check`.
