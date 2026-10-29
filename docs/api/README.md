# EcoTrace API guide

EcoTrace's core and apps are used through HTTP APIs behind one gateway (APISIX). The demo console is only one client of these APIs. A company's own ERP, a mobile app or a script can do everything the console does.

- **Reference page:** `<PUBLIC_URL>/api-docs`, for example <http://localhost:9080/api-docs> locally. Every endpoint, its parameters and its responses, with **Try it out**.
- **OpenAPI documents:** `/intake/openapi.json`, `/ledger/openapi.json`, `/workflow/openapi.json`, `/purchase/openapi.json`.
- **Postman:** import [ecotrace.postman_collection.json](ecotrace.postman_collection.json). `make api-check` runs it with Newman.

| Service | Prefix | What it does |
|---|---|---|
| Document Intake (capability) | `/intake` | Upload documents; malware scan; AI or e-invoice extraction; human review |
| Carbon Ledger (app) | `/ledger` | Activities, approval into Scope 1 and 2 emissions, lineage, period seal, reports, live stream |
| Workflow (capability) | `/workflow` | Approval tasks from each tenant's BPMN processes |
| Purchase Approval (app) | `/purchase` | Purchase requests created from purchase invoices |
| Hasura (core data) | `/v1/graphql` | GraphQL over core tables such as `core.facility` |

## 1. Authentication

Every business call needs a **Keycloak access token** of the `ecotrace` realm in the header `Authorization: Bearer <token>`. The gateway checks the signature, issuer and expiry. Then the service checks the token again (zero trust).

A token lasts 15 minutes. Its claims that matter:

| Claim | Meaning |
|---|---|
| `tenant_id` | The user's company. Every query is limited to it. |
| `realm_access.roles` | `uploader`, `reviewer`, `approver`, `tenant-admin` |
| `preferred_username` | Recorded as the uploader, reviewer or approver |

### In the browser: the reference page

On `/api-docs`:

1. Choose a service under **Select a definition**: Document Intake, Carbon Ledger, Workflow or Purchase Approval.
2. Click **Authorize**.
3. Under **keycloak (OAuth2, authorizationCode with PKCE)**, keep the client id `ecotrace-portal` and leave the client secret empty. Click **Authorize**.
4. Log in as a demo user in the window that opens. The page now sends that user's token with every **Try it out**, for every service.

You can also paste a token under **accessToken (http, Bearer)**.

### From a script: password grant

The `ecotrace-cli` client accepts a user name and password. It exists for scripts and demos. Applications with a browser should use the Authorization Code flow with PKCE (client `ecotrace-portal`), as the console does.

```sh
BASE=http://localhost:9080        # or your PUBLIC_URL
TOKEN=$(curl -s -X POST "$BASE/realms/ecotrace/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=ecotrace-cli \
  -d username=alice --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r .access_token)
```

## 2. A full round trip with curl

This follows a document from upload to a sealed emission figure. Every command below uses `-H "Authorization: Bearer $TOKEN"`.

```sh
auth=(-H "Authorization: Bearer $TOKEN")

# Who am I, which company, which document types does my company accept?
curl -s "${auth[@]}" "$BASE/intake/me" | jq

# Upload an electricity bill: scanned, stored, classified and extracted in one call
DOC=$(curl -s "${auth[@]}" -F file=@tenants/company-a-steel/seed/documents/electricity-bill-2026-09.pdf \
  "$BASE/intake/documents" | jq -r .document.id)

# Read the extracted fields, then correct one value and confirm the document
curl -s "${auth[@]}" "$BASE/intake/documents/$DOC" | jq '.fields'
curl -s "${auth[@]}" -H 'Content-Type: application/json' -d '{"values": {"consumption_kwh": "188800"}}' \
  "$BASE/intake/documents/$DOC/review" | jq
```

The confirmed document becomes an activity in Carbon Ledger, through the `document.reviewed` event. An approver of the same company then approves it:

```sh
# As an.tran (approver), get a token the same way, then:
curl -s "${auth[@]}" "$BASE/workflow/tasks" | jq '.tasks[] | {id, name, title}'
curl -s "${auth[@]}" -H 'Content-Type: application/json' -d '{"approved": true, "comment": "matches the meter"}' \
  "$BASE/workflow/tasks/<task id>/complete"

curl -s "${auth[@]}" "$BASE/ledger/summary?period=2026-09" | jq '{scope1_kg, scope2_kg}'
curl -s "${auth[@]}" "$BASE/ledger/entries/<entry id>/lineage" | jq
curl -s "${auth[@]}" -X POST "$BASE/ledger/periods/2026-09/close" | jq
curl -s "${auth[@]}" "$BASE/ledger/periods/2026-09/verify" | jq '{valid, changed, removed, added}'
curl -s "${auth[@]}" -o inventory.xlsx "$BASE/ledger/report?period=2026-09&format=xlsx"
```

Tenants without a BPMN process for activities, such as a newly onboarded one, approve directly with `POST /ledger/activities/{id}/approve`. When the tenant has a process, that endpoint answers 409 and points to the workflow.

`GET /ledger/stream` is a Server-Sent Events stream. It sends one message per approval, rejection or seal of the caller's company. Read it with `curl -N`, or with `fetch` in a browser so the token stays in a header.

## 3. Tenant isolation and roles

- **Data follows the token.** No endpoint takes a tenant as a parameter. A document, activity or task of another company answers **404**, as if it did not exist. This also holds inside PostgreSQL: the services' roles cannot bypass row-level security (`make rls-check`).
- **Roles come from the company's `org.yaml`:**
  - approving or rejecting an activity and closing a period need `approver`;
  - a workflow task can be completed only by a user with one of the task's candidate groups. Company B's second step, for example, needs `approver`.
- **Modules can be switched off per company in `tenant.yaml`.** A call to a disabled module answers **403**. Company B, for example, does not use Purchase Approval.

## 4. Errors

Errors are JSON: `{"detail": "..."}`.

| Code | When |
|---|---|
| 401 | No token, or the token is expired, forged or from another issuer |
| 403 | Missing role, module disabled for the company, company disabled, token without `tenant_id` |
| 404 | Not found **in your company**. Other companies' data always looks like this. |
| 409 | Duplicate upload (the body names the original document); activity not pending; period already closed; approval must go through the workflow |
| 413 | File larger than 10 MB |
| 415 | File type not accepted (PDF, PNG, JPEG, WebP, e-invoice XML) |
| 422 | Malware found (the file is not stored); invalid e-invoice; unknown field or not a number in a review; bad period or report format |
| 429 | More than 120 requests a minute from one address (gateway rate limit) |
| 503 | Malware scanner or object storage down. The upload is refused rather than accepted unchecked. |

## 5. Events (NATS JetStream)

Services also talk through events, so a new app can react to documents without calling Intake. Events are CloudEvents 1.0 on the stream `ECOTRACE_EVENTS`, with subject `tenant.<tenant_id>.<event>`. A consumer can subscribe to a single company (`tenant.company-a-steel.>`) or to all of them (`tenant.*.document.reviewed`). See [ADR-0003](../adr/0003-event-subjects-and-envelope.md).

```json
{
  "specversion": "1.0",
  "id": "4f1c…",
  "source": "/capabilities/document-intake",
  "type": "vn.ecotrace.document.reviewed.v1",
  "subject": "<document id>",
  "time": "2026-10-29T08:00:00+00:00",
  "datacontenttype": "application/json",
  "tenantid": "company-a-steel",
  "traceid": "…",
  "data": { "document_id": "…", "document_type": "electricity_bill", "fields": { "consumption_kwh": "188800" } }
}
```

| Event | Published by | Used by |
|---|---|---|
| `document.received` | Document Intake | |
| `document.extracted` | Document Intake | Purchase Approval (when no review is needed) |
| `document.reviewed` | Document Intake | Carbon Ledger, Purchase Approval |
| `workflow.requested` | Carbon Ledger, Purchase Approval | Workflow |
| `workflow.completed` | Workflow | Carbon Ledger, Purchase Approval |
| `workflow.unavailable` | Workflow | |
| `ledger.sealed` | Carbon Ledger | |

`make events TENANT=company-a-steel` prints the latest events of a company.

## 6. GraphQL (Hasura)

Core tables are also readable through GraphQL with the same token. Rows are filtered by the token's `tenant_id`.

```sh
curl -s "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"query": "{ core_facility(order_by: {name: asc}) { code name kind province } }"}' \
  "$BASE/v1/graphql" | jq
```

## 7. Postman

1. Import [ecotrace.postman_collection.json](ecotrace.postman_collection.json).
2. Open the collection's **Variables** and set `baseUrl` (your `PUBLIC_URL`), `username` and `password`.
3. Send any request. The collection gets a token before the first request and again when the token expires.

To act as another user, change `username` (and `password`): the next request logs in again.
