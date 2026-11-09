#!/bin/sh
# SPDX-FileCopyrightText: 2026 EcoTrace contributors
# SPDX-License-Identifier: Apache-2.0
# Downloads Trillian's PostgreSQL schema from its pinned release instead of keeping a copy in this repository.
# Run by `make up`; the db-migrate service applies the file to an empty trillian database.
set -eu

VERSION=v1.8.0
URL="https://raw.githubusercontent.com/google/trillian/$VERSION/storage/postgresql/schema/storage.sql"
SHA256=1142d2a1e5ac126b4c48fa2a3a822d83342dd5f03e59c1cc8d5e8addc414007e
TARGET="$(dirname "$0")/storage.sql"

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

if [ -f "$TARGET" ] && [ "$(sha256 "$TARGET")" = "$SHA256" ]; then
  exit 0
fi
curl -fsSL --retry 3 "$URL" -o "$TARGET.part"
if [ "$(sha256 "$TARGET.part")" != "$SHA256" ]; then
  rm -f "$TARGET.part"
  echo "Trillian schema $VERSION: checksum mismatch, refusing to use it ($URL)" >&2
  exit 1
fi
mv "$TARGET.part" "$TARGET"
echo "Trillian schema $VERSION downloaded and verified"
