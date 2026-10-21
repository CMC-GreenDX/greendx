# demo-console

A small static console (HTML, CSS, JavaScript, no build step) that shows how EcoTrace works end to end. The Nuxt 3 portal from the [project brief](../../docs/project-brief.md) replaces it in Phase 6.

- Login with Keycloak (Authorization Code + PKCE, client `ecotrace-portal`); the page shows the user, the tenant and the AI mode.
- Upload a document or one of the tenant's sample documents, and watch the processing pipeline, the detected type and the extracted fields with their confidence.
- Open the original document next to the extracted values.
- The tenant's document list and facilities (GraphQL through the gateway).
- UI strings come from `public/i18n/vi.json` and `public/i18n/en.json`.

It is served by nginx behind the gateway at <http://localhost:9080/>, so every API call goes to the same origin and carries the access token.
