# purchase-approval

A deliberately tiny second app (brief section 6). Confident or reviewed purchase invoices from Document Intake start the tenant's `purchase-approval` BPMN process through the workflow capability, and the decision is stored in `purchase.request` (row-level security, role `purchase_app`).

It is enabled per tenant with `modules.purchase-approval` in `tenant.yaml` plus `workflows/purchase-approval.bpmn`. Company A has it; Company B has it disabled. It reuses the core, Document Intake and the workflow without any change to them. This is the point of the app.

API: `GET /purchase/requests`. Test: `make workflow-check`.
