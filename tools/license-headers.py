# SPDX-FileCopyrightText: 2026 EcoTrace contributors
# SPDX-License-Identifier: Apache-2.0
"""Checks, or adds with --fix, the SPDX license header of every source file in the repository.

    python tools/license-headers.py          # list files without a header, exit 1 if any
    python tools/license-headers.py --fix    # add the header where it is missing

Data files (JSON, sample documents, Markdown) and third-party files are not source files and are skipped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

COPYRIGHT = "SPDX-FileCopyrightText: 2026 EcoTrace contributors"
LICENSE = "SPDX-License-Identifier: Apache-2.0"

HASH = ("# ", "")
STYLES = {
    ".py": HASH, ".sh": HASH, ".yml": HASH, ".yaml": HASH, ".toml": HASH, ".conf": HASH, ".txt": HASH,
    ".example": HASH, ".editorconfig": HASH, ".gitignore": HASH, ".gitattributes": HASH, ".npmrc": HASH,
    "Dockerfile": HASH, "Makefile": HASH,
    ".go": ("// ", ""), ".js": ("// ", ""), ".mjs": ("// ", ""),
    ".css": ("/* ", " */"), ".sql": ("-- ", ""),
    ".html": ("<!-- ", " -->"), ".bpmn": ("<!-- ", " -->"),
}
# Copies of other projects keep their own notices.
SKIP = {"deploy/compose/trillian/storage.sql"}


def style_of(path: str) -> tuple[str, str] | None:
    name = Path(path).name
    if path in SKIP:
        return None
    return STYLES.get(name) or STYLES.get(Path(path).suffix)


def insert_at(lines: list[str]) -> int:
    """Index after a first line that must stay first: shebang, XML declaration or HTML doctype."""
    if lines and (lines[0].startswith("#!") or lines[0].startswith("<?xml") or lines[0].lower().startswith("<!doctype")):
        return 1
    return 0


def main() -> int:
    fix = "--fix" in sys.argv[1:]
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    missing = []
    for path in files:
        style = style_of(path)
        if style is None or not Path(path).is_file():
            continue
        text = Path(path).read_text(encoding="utf-8")
        if LICENSE in "\n".join(text.splitlines()[:5]):
            continue
        missing.append(path)
        if fix:
            start, end = style
            lines = text.splitlines(keepends=True)
            at = insert_at(lines)
            header = [f"{start}{COPYRIGHT}{end}\n", f"{start}{LICENSE}{end}\n"]
            Path(path).write_text("".join(lines[:at] + header + lines[at:]), encoding="utf-8", newline="")
    for path in missing:
        print(("added header: " if fix else "missing header: ") + path)
    if missing and not fix:
        print(f"{len(missing)} file(s) without an SPDX header; run: python tools/license-headers.py --fix")
        return 1
    print(f"SPDX headers: {'added to ' + str(len(missing)) if fix else 'present in every'} source file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
