# demo-console

A static console (HTML, CSS, JavaScript, no build step) that shows how EcoTrace works end to end. Its menu has Upload, Approvals, Carbon Ledger, Purchase requests, Documents and Facilities. Unavailable app modules are hidden for the current company.

- Login with Keycloak (Authorization Code + PKCE, client `ecotrace-portal`); the page shows the user, the tenant and the AI mode.
- Upload a document or one of the tenant's sample documents, and watch the processing pipeline, the detected type and the extracted fields with their confidence.
- Open the original document next to the extracted values.
- The tenant's document list and facilities (GraphQL through the gateway).
- UI strings come from `public/i18n/vi.json` and `public/i18n/en.json`.

It is served by nginx behind the gateway at <http://localhost:9080/>, so every API call goes to the same origin and carries the access token.

The visual tokens and fonts are defined in `public/styles.css`. `public/navigation.js` manages the screen layout and derives the approval count from the existing inbox; `public/app.js` continues to own authentication, data and actions. Both language dictionaries retain their existing keys. Google Fonts supplies Be Vietnam Pro and IBM Plex Mono with `display=swap`; Arial and monospace remain available offline.

## Checks

- `make console-layout-check`: Chromium tests against API fixtures, without a running stack. Covers navigation, language switching, upload and review, module visibility, original documents, lineage, exports and sealing, plus overflow and 44 px buttons at 360, 375, 600, 768, 1024 and 1440 px. These are synthetic responses, not an integration test of the backend.
- `make ui-check`: the existing live SSO, tenant isolation and API-reference test against a running stack. It now follows the menu between screens.

For a local Playwright installation, run `python deploy/compose/demo/console-layout-check.py` from the repository root. Fixture screenshots are written to the system temporary directory under `ecotrace-console-layout`, or to `SCREENSHOT_DIR` when set.
