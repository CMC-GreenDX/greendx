# capabilities

Tier 2 capability spaces. Reusable services that know nothing about a specific business domain or tenant. They talk to the core only through the API gateway and the event bus.

| Folder | Space | Purpose |
|---|---|---|
| `document-intake/` | [I] Intelligence | Upload, malware scan, OCR, classification and field extraction |
| `portal/` | [H] Human | Single web portal (Nuxt 3) with SSO |
| `workflow-ui/` | [P] Process | "My approvals" task inbox |
| `dashboard/` | [D] Data | Real-time and historical analytics |
