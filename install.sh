#!/bin/bash
# Install the mandor skill into ~/.claude/skills/mandor.
# An existing install is left alone unless --force is given; with --force it is backed up first.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/skills"
BACKUPS="$HOME/.claude/skill-backups"   # outside skills/, so Claude Code never loads a stale copy
FORCE="${1:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

place() { # place <src> <dest>
  local src="$1" dst="$2"
  if [ -e "$dst" ]; then
    if diff -rq -x __pycache__ -x .DS_Store "$src" "$dst" >/dev/null 2>&1; then
      echo "   ok   $dst (already up to date)"; return
    fi
    if [ "$FORCE" != "--force" ]; then
      echo "   skip $dst exists and differs. Merge it by hand, or re-run with --force"
      return
    fi
    mkdir -p "$BACKUPS"
    mv "$dst" "$BACKUPS/$(basename "$dst").bak-$STAMP"
    echo "   backup -> $BACKUPS/$(basename "$dst").bak-$STAMP"
  fi
  cp -R "$src" "$dst"
  chmod +x "$dst"/scripts/*.py
  echo "   ok   $dst"
}

place "$SRC/skills/mandor" "$DEST/mandor"

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "   WARNING: python3 not found. The skill is installed, but its check scripts and the"
  echo "   guard hook need python3 (install Xcode Command Line Tools: xcode-select --install)."
fi
