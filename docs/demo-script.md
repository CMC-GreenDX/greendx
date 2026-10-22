# Demo script

This script covers what is built for the organiser demo on 2026-10-22: the identity, gateway and data slice of the core, and the Document Intake capability with a demo console. The full product demo from the [project brief](project-brief.md) (section 11) is added phase by phase.

## Before the demo (15 minutes ahead)

1. Open the codespace in **VS Code desktop**: on GitHub, **Code → Codespaces → ecotrace-demo → Open in Visual Studio Code**. VS Code forwards the ports to `localhost` on your own computer, which the Keycloak login needs.
2. In the codespace terminal, wait a few seconds for Docker to start, then run:

   ```sh
   make up            # PostgreSQL, Keycloak, Hasura, Document Intake, demo console, APISIX
   make health        # every line must say OK
   make demo          # four PASS lines (terminal demo of the core)
   make intake-check  # upload, extraction and tenant isolation
   ```

3. Check the AI mode: `make intake-check` prints `AI {"enabled":true,...}` when `GEMINI_API_KEY` is available (a Codespaces secret). Without it, the rule-based fallback is used and photos are not recognised.
4. Open <http://localhost:9080> in your browser and log in once as `alice` to check that everything loads. The demo password is `DEMO_USER_PASSWORD` in `.env`.

If something fails: `make logs` shows the service logs, and `make reset && make up` starts again from an empty database.

## Live demo in the browser (about 8 minutes)

| Step | What to do | What to say |
|---|---|---|
| 1 | Open <http://localhost:9080>, click **Đăng nhập bằng SSO**, log in as `alice` | One login through Keycloak. The token carries the company (tenant); the gateway and every service verify it. |
| 2 | Point at the top bar and the configuration strip | Alice works for Company A (steel). Her company's configuration accepts three document types with an 80% confidence threshold. That is a YAML file in the tenant's config pack, not code. |
| 3 | Click **Tải lên** next to the electricity bill sample | Watch the pipeline: token verified, malware scan by ClamAV, file stored in Company A's own storage, AI classifies and extracts using Company A's configuration, result saved and linked to the original. |
| 4 | Point at the extracted fields | 188,800 kWh, billing period and total amount, each with a confidence score. Anything below the threshold is flagged for a person to review: we never trust AI blindly. |
| 5 | Click **Xem tài liệu gốc** | Every number can be traced back to its source document. This is the basis of the emission lineage the jury will see later. |
| 6 | Upload the warehouse issue slip photo | A phone photo of a paper slip, in Vietnamese: the AI reads it directly, without a separate OCR step. |
| 7 | Switch to **EN** and back | All UI text comes from translation files (Vietnamese and English). |
| 8 | Log out, log in as `bob` | Company B (logistics) has a different configuration: it accepts fuel slips but not warehouse slips, with an 85% threshold. Bob does not see any of Alice's documents or facilities. |
| 9 | Upload Bob's fuel slip photo | Same code, different company configuration: 185.4 litres of diesel, ready for Scope 1 later. |

Optional, events: `make events TENANT=company-a-steel` prints the CloudEvents that Intake published for the last upload, including the extracted fields. This is what Carbon Ledger will consume.

Optional, malware scan: in the terminal, `make intake-check` uploads the EICAR antivirus test file and shows it is rejected (HTTP 422) and never stored.

Optional, in the terminal: `make demo` shows that a call without a token, or with a token whose tenant was edited by hand, is rejected with 401.

## Questions to expect

- **"You send company invoices to an external AI?"** Yes, when AI extraction is on. It is optional and per deployment. Without a key, a rule-based fallback runs entirely on-premise. Before production, each company must opt in. See [ADR-0002](adr/0002-hosted-llm-api-for-document-intake.md).
- **"Gemini is free, so what does Google do with the data?"** On the free tier Google may use the content to improve its products, so we only send fictional sample documents. Real deployments use a paid tier, another provider, or the on-premise fallback.
- **"Is the AI open source?"** No. Gemini (and the optional Claude provider) are hosted services and is not shipped with EcoTrace. Everything we ship is under OSI licenses ([docs/licenses.md](licenses.md)), and the extractor can be switched to a local model later.
- **"Is isolation enforced in the database?"** Today it is enforced by the gateway (signature), the services (tenant claim on every query) and Hasura permissions. PostgreSQL row-level security comes in Phase 2.
- **"Where are the other core services?"** OpenBao, Flowable, Kestra, Trillian and observability are the remaining Phase 1 work. Their choices and licenses are in [ADR-0001](adr/0001-core-technology-choices.md).

## Consoles (optional)

| Console | URL | Login |
|---|---|---|
| Keycloak (users, `tenant_id` attribute, token mapper) | <http://localhost:8080/admin/master/console/#/ecotrace> | `admin` / `KC_ADMIN_PASSWORD` from `.env` |
| Hasura (`demo.facility` and its row filter) | <http://localhost:8081/console> | `HASURA_ADMIN_SECRET` from `.env` |
