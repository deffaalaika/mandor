#!/bin/bash
# End-to-end test for build-release.sh + get-mandor.sh + install.sh, in a temporary HOME.
# Usage: bash tests/test_install.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
mkdir -p "$HOME"
DEST="$HOME/.claude/skills/mandor"
PASS=0
FAIL=0

ok()   { PASS=$((PASS + 1)); echo "  ok   $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "  FAIL $1"; }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

echo "== build"
bash "$ROOT/build-release.sh" "$TMP/dist" >/dev/null
check "zip built" '[ -f "$TMP/dist/mandor.zip" ]'
check "SHA256SUMS built" 'grep -q " mandor.zip$" "$TMP/dist/SHA256SUMS"'
check "zip has no __pycache__" '! unzip -l "$TMP/dist/mandor.zip" | grep -q __pycache__'
check "zip has no tests" '! unzip -l "$TMP/dist/mandor.zip" | grep -q "tests/"'

echo "== first install"
out="$(bash "$ROOT/get-mandor.sh" "$TMP/dist" 2>&1)"
check "SKILL.md installed" '[ -f "$DEST/SKILL.md" ]'
check "check_plan.py installed" '[ -f "$DEST/scripts/check_plan.py" ]'
check "guard.py executable" '[ -x "$DEST/scripts/guard.py" ]'
run_out="$(/usr/bin/python3 "$DEST/scripts/check_plan.py" "$TMP/nope" 2>&1 || true)"
check "installed scripts run" 'echo "$run_out" | grep -q "RESULT: FAIL"'
check "scripts leave no __pycache__" '[ ! -d "$DEST/scripts/__pycache__" ]'

echo "== reinstall (unchanged, even after scripts created __pycache__)"
mkdir -p "$DEST/scripts/__pycache__" && touch "$DEST/scripts/__pycache__/x.pyc"
out="$(bash "$ROOT/get-mandor.sh" "$TMP/dist" 2>&1)"
check "already up to date" 'echo "$out" | grep -q "already up to date"'

echo "== reinstall over local edits without --force"
echo "local edit" >> "$DEST/SKILL.md"
out="$(bash "$ROOT/get-mandor.sh" "$TMP/dist" 2>&1)"
check "skip without --force" 'echo "$out" | grep -q "skip"'
check "local edit kept" 'grep -q "local edit" "$DEST/SKILL.md"'

echo "== reinstall with --force"
out="$(bash "$ROOT/get-mandor.sh" "$TMP/dist" --force 2>&1)"
check "backup created outside skills dir" 'ls -d "$HOME/.claude/skill-backups/"mandor.bak-* >/dev/null 2>&1'
check "no backup inside skills dir" '! ls -d "$HOME/.claude/skills/"mandor.bak-* >/dev/null 2>&1'
check "local edit replaced" '! grep -q "local edit" "$DEST/SKILL.md"'

echo "== checksum mismatch"
mkdir -p "$TMP/bad"
cp "$TMP/dist/mandor.zip" "$TMP/bad/"
echo "0000000000000000000000000000000000000000000000000000000000000000  mandor.zip" > "$TMP/bad/SHA256SUMS"
if bash "$ROOT/get-mandor.sh" "$TMP/bad" >/dev/null 2>&1; then rc=0; else rc=$?; fi
check "exit non-zero" '[ "$rc" -ne 0 ]'
check "bad zip deleted" '[ ! -f "$TMP/bad/mandor.zip" ]'

echo
echo "passed: $PASS, failed: $FAIL"
[ "$FAIL" -eq 0 ]
