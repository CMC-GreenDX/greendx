# tenants

Tenant config packs. A tenant is one company, onboarded by configuration only. Each pack is validated against the schemas in `core/schemas/` and applied with `dxctl`.

| File | Contents | Schema |
|---|---|---|
| `tenant.yaml` | Id, name, locale, enabled modules | `core/schemas/tenant.schema.json` |
| `org.yaml` | Departments, users and their roles | `core/schemas/org.schema.json` |
| `document-types.yaml` | Documents Intake accepts and the fields to extract | `core/schemas/document-types.schema.json` |
| `emission-sources.yaml` | Facilities and emission sources | `core/schemas/emission-sources.schema.json` |
| `seed/` | Fictional sample documents | |

Packs: `company-a-steel` and `company-b-logistics` (seeded by `make up`), `company-c-cement` (for the live onboarding demo). See [tools/dxctl](../tools/dxctl/README.md).
