#!/bin/bash
# Build the release package: <out>/mandor.zip + <out>/SHA256SUMS.
# Upload both files to a GitHub Release of deffaalaika/mandor.
#
# Usage: bash build-release.sh [<out-dir>]   (default: ./dist)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$ROOT/dist}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/mandor/skills"
cp "$ROOT/install.sh" "$STAGE/mandor/"
cp -R "$ROOT/skills/mandor" "$STAGE/mandor/skills/"
find "$STAGE" \( -name __pycache__ -o -name .DS_Store \) -prune -exec rm -rf {} +

rm -f "$OUT/mandor.zip" "$OUT/SHA256SUMS"
(cd "$STAGE" && zip -qr "$OUT/mandor.zip" mandor)
(cd "$OUT" && shasum -a 256 mandor.zip > SHA256SUMS)
echo "Built: $OUT/mandor.zip"
cat "$OUT/SHA256SUMS"
