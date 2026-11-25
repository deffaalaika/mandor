#!/bin/bash
# Download the mandor package from this repo's GitHub Release, verify it,
# unzip it and install it into ~/.claude/skills/mandor (no GitHub login needed).
#
# Usage:
#   bash get-mandor.sh                 # download into ./mandor-download, then install
#   bash get-mandor.sh <dir>           # use files already downloaded into <dir>
#   bash get-mandor.sh [<dir>] --force # also replace an existing install (old one is backed up)
set -euo pipefail

REPO="deffaalaika/mandor"
BASE="https://github.com/$REPO/releases/latest/download"
ZIP="mandor.zip"

FORCE=""
DIR=""
for a in "$@"; do
  case "$a" in
    --force) FORCE="--force" ;;
    *) DIR="$a" ;;
  esac
done
EXPLICIT_DIR="$DIR"
DIR="${DIR:-$PWD/mandor-download}"
mkdir -p "$DIR"
cd "$DIR"

info() { printf '\033[36m==> %s\033[0m\n' "$*"; }
die()  { printf '\033[31m%s\033[0m\n' "$*"; exit 1; }

# 1. Checksums + package (default folder: always fetch the latest; <dir>: use what is there)
if [ -z "$EXPLICIT_DIR" ]; then
  rm -f SHA256SUMS "$ZIP"
fi
for f in SHA256SUMS "$ZIP"; do
  if [ ! -f "$f" ]; then
    info "Downloading $f"
    curl -fL --retry 5 --retry-delay 3 -o "$f" "$BASE/$f"
  fi
done

# 2. Verify
want="$(grep " $ZIP\$" SHA256SUMS | awk '{print $1}')"
[ -n "$want" ] || die "No checksum for $ZIP in SHA256SUMS"
got="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
if [ "$got" != "$want" ]; then
  rm -f "$ZIP" SHA256SUMS
  die "Checksum mismatch for $ZIP. It was deleted; run this script again."
fi
echo "   ok   $ZIP"

# 3. Unzip + install
info "Unzipping"
rm -rf mandor
unzip -q "$ZIP"
bash mandor/install.sh $FORCE

echo
echo "Done. Start a new Claude Code session and type /mandor. You can now delete: $DIR"
