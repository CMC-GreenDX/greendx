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

## Sharing a public link

Use this when the teacher or the organisers should open EcoTrace from their own computers. Everything goes through the gateway on port 9080: the console, the APIs and the Keycloak login pages. Hasura, the Keycloak admin console, PostgreSQL and the other ports stay private to the codespace.

1. In the codespace terminal, run `make public-url` and put the address it prints in `.env` as `PUBLIC_URL`.
2. In `.env`, replace `DEMO_USER_PASSWORD` with a new password. `change-me-demo` is published in this repository, so anyone could use it.
3. Run `make up`, then `make demo-password` to give every demo user the new password.
4. Make port 9080 public: in VS Code, open **Ports**, right-click 9080 and choose **Port Visibility → Public**. From a terminal outside the codespace, run `gh codespace ports visibility 9080:public -c <codespace>`.
5. Open the public address in a private browser window and log in as `alice` to check.

Rules for a public link:

- Upload only the fictional sample documents. On the free Gemini tier, Google may use the content.
- The link works only while the codespace runs. It stops after 30 minutes without activity, and every hour is billed to the codespace owner.
- When you are done, set the port back to **Private**, or stop the codespace.
- To go back to working on `localhost`, remove `PUBLIC_URL` from `.env` and run `make up` again.

## Live demo in the browser (about 8 minutes)

| Step | What to do | What to say |
|---|---|---|
| 1 | Open <http://localhost:9080>, click **Đăng nhập bằng SSO**, log in as `alice` | One login through Keycloak. The token carries the company (tenant); the gateway and every service verify it. |
| 2 | Point at the top bar and the configuration strip | Alice works for Company A (steel). Her company's configuration accepts three document types with an 80% confidence threshold. That is a YAML file in the tenant's config pack, not code. |
| 3 | Click **Tải lên** next to the electricity bill sample | Watch the pipeline: token verified, malware scan by ClamAV, file stored in Company A's own storage, AI classifies and extracts using Company A's configuration, result saved and linked to the original. |
| 4 | Point at the extracted fields | 188,800 kWh, billing period and total amount, each with a confidence score. Anything below the threshold is flagged for a person to review: we never trust AI blindly. |
| 4b | Click **Duyệt / sửa**, change a value, click **Lưu và xác nhận** | A person always has the last word. The correction history keeps the old value, the new value, who changed it and when, and the reviewed values are published for Carbon Ledger. |
| 4c | Click **Tải lên** on the same sample again | The same bill is not stored twice, so its emissions cannot be counted twice. |
| 5 | Click **Xem tài liệu gốc** | Every number can be traced back to its source document. This is the basis of the emission lineage the jury will see later. |
| 6 | Upload the warehouse issue slip photo | A phone photo of a paper slip, in Vietnamese: the AI reads it directly, without a separate OCR step. |
| 7 | Switch to **EN** and back | All UI text comes from translation files (Vietnamese and English). |
| 7b | In the terminal: `make dxctl ARGS="tenant create tenants/company-c-cement"`, then log in as `chi.pham` | A new company is onboarded in seconds from four YAML files: users, roles, storage bucket, facilities. No code change, no restart. |
| 7c | Log out, log in as `an.tran` (approver, Company A). In **Việc cần duyệt**, click **Phê duyệt** | The reviewed bill became an activity through the event bus, and Company A's own BPMN process (one step, from its config pack) put an approval task in the approver's inbox. Approving turns it into 128.57 tCO₂e in Scope 2. Click the figure to see its lineage: original bill, reviewer and corrections, approver, factor version and citation. |
| 7c-bis | Keep the dashboard open while approving | The dashboard is connected live (Server-Sent Events): the Scope 2 bar appears the moment the approval lands, without reloading. |
| 7d | Still as `an.tran`: choose period **2026-09**, click **Khoá kỳ & niêm phong**, then **Kiểm tra niêm phong** (green). In the terminal run `make tamper`, then click **Kiểm tra niêm phong** again (red, names the bill); `make untamper` | Closing a period writes a fingerprint of every figure into a Trillian verifiable log, the same technology as Certificate Transparency. Someone who edits the database directly cannot hide it: the check reads the seal back from the log and names the changed entry. |
| 8 | Log out, log in as `bob` | Company B (logistics) has a different configuration: it accepts fuel slips but not warehouse slips, with an 85% threshold. Bob does not see any of Alice's documents or facilities. |
| 8b | As `bob`, upload and confirm Bob's electricity bill; Bob sees step 1 "Đội xe kiểm tra" in his inbox. After he approves, step 2 goes to `binh.le` (finance) | Same code, different company: Company B's BPMN has two steps. Who sees which task comes from roles in `org.yaml`. |
| 8c | As `alice`, upload a purchase invoice | It goes to Purchase Approval, not the emission ledger: a second app reuses the same intake, events and workflow. Company B has this module disabled. |
| 8d | Upload the sample **e-invoice XML** | Most Vietnamese invoices are e-invoices: their values are read straight from the XML, exact, free and with no AI. |
| 8e | In the ledger, click **Xuất Excel** | The inventory report the company submits: totals by scope, every figure with its source document, factor version, reviewer and approver. |
| 9 | Upload Bob's fuel slip photo | Same code, different company configuration: 185.4 litres of diesel, ready for Scope 1 later. |

Optional, events: `make events TENANT=company-a-steel` prints the CloudEvents that Intake published for the last upload, including the extracted fields. This is what Carbon Ledger will consume.

Optional, malware scan: in the terminal, `make intake-check` uploads the EICAR antivirus test file and shows it is rejected (HTTP 422) and never stored.

Optional, API: open `/api-docs`, click **Authorize** and log in as `alice`. Then use **Try it out** on `GET /intake/documents`. The same API the console uses is open to any other application, and it returns only Company A's documents. See the [API guide](api/README.md).

Optional, in the terminal: `make demo` shows that a call without a token, or with a token whose tenant was edited by hand, is rejected with 401.

## Questions to expect

- **"You send company invoices to an external AI?"** Yes, when AI extraction is on. It is optional and per deployment. Without a key, a rule-based fallback runs entirely on-premise. Before production, each company must opt in. See [ADR-0002](adr/0002-hosted-llm-api-for-document-intake.md).
- **"Gemini is free, so what does Google do with the data?"** On the free tier Google may use the content to improve its products, so we only send fictional sample documents. Real deployments use a paid tier, another provider, or the on-premise fallback.
- **"Is the AI open source?"** No. Gemini (and the optional Claude provider) are hosted services and is not shipped with EcoTrace. Everything we ship is under OSI licenses ([docs/licenses.md](licenses.md)), and the extractor can be switched to a local model later.
- **"Is isolation enforced in the database?"** Yes. Services connect with roles that cannot bypass PostgreSQL row-level security, and `make rls-check` shows that a query explicitly asking for another company's rows returns nothing, and that a forged insert is rejected ([ADR-0004](adr/0004-tenant-model.md)).
- **"Where are the other core services?"** OpenBao, Flowable, Kestra, Trillian and observability are the remaining Phase 1 work. Their choices and licenses are in [ADR-0001](adr/0001-core-technology-choices.md).

## Consoles (optional)

| Console | URL | Login |
|---|---|---|
| Keycloak (users, `tenant_id` attribute, token mapper) | <http://localhost:8080/admin/master/console/#/ecotrace> | `admin` / `KC_ADMIN_PASSWORD` from `.env` |
| Hasura (`demo.facility` and its row filter) | <http://localhost:8081/console> | `HASURA_ADMIN_SECRET` from `.env` |
