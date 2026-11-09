# SPDX-FileCopyrightText: 2026 EcoTrace contributors
# SPDX-License-Identifier: Apache-2.0
"""Writes the OpenAPI document of every service to a folder, without starting the services.

Used by the GitHub Pages workflow (.github/workflows/pages.yml). Run from the repository root, with the services' requirements installed:

    python tools/api-docs/export_openapi.py _site/api/openapi
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVICES = {
    "intake": "capabilities/document-intake",
    "ledger": "apps/carbon-ledger",
    "workflow": "capabilities/workflow-ui",
    "purchase": "apps/purchase-approval",
}
# Every service is a package named `app`, so each one is imported in its own interpreter.
DUMP = "import json, sys; from app.main import app; json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)"


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site/api/openapi")
    out.mkdir(parents=True, exist_ok=True)
    # The login URLs in the documents point at a local stack; a deployment serves its own copy at /<service>/openapi.json.
    env = {**os.environ, "JWT_ISSUER": os.environ.get("JWT_ISSUER", "http://localhost:9080/realms/ecotrace")}
    for prefix, path in SERVICES.items():
        target = out / f"{prefix}.json"
        with target.open("w", encoding="utf-8") as handle:
            subprocess.run([sys.executable, "-c", DUMP], cwd=path, env=env, stdout=handle, check=True)
        print(f"{prefix:<9} {path} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
