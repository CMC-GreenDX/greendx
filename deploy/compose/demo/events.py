"""Shows the latest document events of a tenant from NATS JetStream. Runs inside the document-intake container.

Usage: make events TENANT=company-a-steel        (prints the latest events)
       python - <tenant> <document_id>          (exit code 1 if that document's events are missing)
"""

import asyncio
import json
import sys

import nats

STREAM = "ECOTRACE_EVENTS"
EVENTS = ["document.received", "document.extracted"]


async def main(tenant: str, document_id: str | None) -> int:
    nc = await nats.connect("nats://nats:4222")
    js = nc.jetstream()
    ok = True
    for event in EVENTS:
        subject = f"tenant.{tenant}.{event}"
        try:
            msg = await js.get_last_msg(STREAM, subject)
        except nats.js.errors.NotFoundError:
            print(f"{subject}: no event")
            ok = False
            continue
        envelope = json.loads(msg.data)
        data = envelope["data"]
        print(f"{subject}  (seq {msg.seq})")
        print("  " + json.dumps({k: envelope[k] for k in ("specversion", "type", "source", "subject", "tenantid", "time")},
                                ensure_ascii=False))
        summary = {k: data[k] for k in ("document_id", "document_type", "status", "storage_uri") if k in data}
        if "fields" in data:
            summary["fields"] = {f["name"]: f["value"] for f in data["fields"]}
        print("  data: " + json.dumps(summary, ensure_ascii=False))
        if document_id and data.get("document_id") != document_id:
            ok = False
    await nc.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)))
