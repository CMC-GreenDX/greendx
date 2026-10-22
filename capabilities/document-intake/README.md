# document-intake

Document Intake capability (Python FastAPI). It turns an uploaded PDF or photo into a classified document with extracted fields and a confidence score per field. It knows nothing about carbon or about any specific company: document types and fields come from the tenant's config pack (`tenants/<tenant>/document-types.yaml`).

## Flow

1. The gateway verifies the access token; the service verifies it again and reads the `tenant_id` claim.
2. The file is streamed to ClamAV (clamd INSTREAM). Infected files are rejected with 422 and never stored; if the scanner is down, the upload is refused with 503 (fail closed).
3. The original file is stored under the tenant's own folder (moves to a per-tenant SeaweedFS bucket later in Phase 1).
4. Classification and extraction:
   - with the provider's key (`GEMINI_API_KEY` by default, or `ANTHROPIC_API_KEY` with `AI_PROVIDER=claude`): the LLM reads the PDF or image and answers in a JSON schema built from the tenant's config ([ADR-0002](../../docs/adr/0002-hosted-llm-api-for-document-intake.md));
   - without a key, or if the API fails: a rule-based fallback (keywords and regular expressions from the same config).
5. Values are normalised (numbers, ISO dates); fields below the tenant's `review_threshold` are flagged for review.
6. The document and its fields are stored in PostgreSQL (`intake` schema), always scoped by `tenant_id`.

Not yet: events on the bus, and the review workflow (later Phase 1 issues and Phase 4).

## API (through the gateway, bearer token required)

| Method and path | Purpose |
|---|---|
| `GET /intake/me` | User, tenant, AI mode and the tenant's document types |
| `POST /intake/documents` | Upload a file (multipart field `file`; PDF, PNG, JPEG, WebP; up to 10 MB) |
| `GET /intake/documents` | The tenant's documents, newest first |
| `GET /intake/documents/{id}` | One document with its fields |
| `GET /intake/documents/{id}/file` | The original file |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AI_PROVIDER` | `gemini` | `gemini` or `claude` |
| `GEMINI_API_KEY` | unset | Enables Gemini extraction. Provide it from the environment only (for example a Codespaces secret) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model |
| `ANTHROPIC_API_KEY` | unset | Enables Claude extraction when `AI_PROVIDER=claude` |
| `CLAUDE_MODEL` / `CLAUDE_EFFORT` | `claude-opus-5-5` / `low` | Claude model and effort |
| `TENANTS_DIR` | `/config/tenants` | Where tenant config packs are mounted |

Tests: `make intake-check` (API and tenant isolation) and `make ui-check` (browser).
