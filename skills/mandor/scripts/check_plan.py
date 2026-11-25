#!/usr/bin/env python3
"""Validate a mandor plan folder against references/plan-format.md.

Usage: check_plan.py <plan-dir>
Exit: 0 = PASS, 1 = FAIL, 2 = usage error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.dont_write_bytecode = True  # keep the installed skill folder clean
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mandor_plan as mp  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
META_KEYS = ["repo", "base", "steps", "revision", "status", "created", "task"]
_MISSING = object()


def _git_ok(repo: Path, *args: str) -> bool:
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True)
    return r.returncode == 0


def _is_inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


class VirtualTree:
    """File contents as they will be after the steps applied so far."""

    def __init__(self, repo: Path, base: str) -> None:
        self.repo = repo
        self.base = base
        self.files: Dict[str, object] = {}

    def get(self, path: str) -> Optional[str]:
        val = self.files.get(path, _MISSING)
        if val is _MISSING:
            val = mp.git_show(self.repo, self.base, path)
            self.files[path] = val
        return val  # type: ignore[return-value]

    def set(self, path: str, content: Optional[str]) -> None:
        self.files[path] = content


def check_step(step_path: Path, tree: VirtualTree, rules: str, rep: mp.Report) -> None:
    step = mp.parse_step(step_path)
    n = step.number
    for e in step.errors:
        rep.add("FAIL", e, n)
    if step.sections.get("EXECUTOR RULES", "").strip() != rules:
        rep.add("FAIL", "executor rules block modified (must be references/executor-rules.md verbatim)", n)

    if not step.changes:
        rep.add("FAIL", "FILES TO CHANGE is empty", n)
    if len(step.changes) > mp.MAX_FILES_PER_STEP:
        rep.add("FAIL", "more than %d files in FILES TO CHANGE (%d)" % (mp.MAX_FILES_PER_STEP,
                                                                         len(step.changes)), n)
    listed = [c.path for c in step.changes]
    for p in set(listed):
        if listed.count(p) > 1:
            rep.add("FAIL", "file listed twice: %s" % p, n)
    for b in step.blocks:
        if b.path not in listed:
            rep.add("FAIL", "block for unlisted file %s" % b.path, n)

    # what the model reads: FILES TO READ ranges + current content of files it modifies
    read_chars = 0
    for r in step.reads:
        content = tree.get(r.path)
        if content is None:
            rep.add("FAIL", "FILES TO READ file %s does not exist" % r.path, n)
            continue
        file_lines = content.splitlines()
        if r.end > len(file_lines):
            rep.add("FAIL", "FILES TO READ %s:%d-%d out of range (file has %d lines)"
                    % (r.path, r.start, r.end, len(file_lines)), n)
            continue
        read_chars += len("\n".join(file_lines[r.start - 1:r.end]))

    for c in step.changes:
        blocks = [b for b in step.blocks if b.path == c.path]
        current = tree.get(c.path)
        if c.action == "CREATE":
            if current is not None:
                rep.add("FAIL", "CREATE %s but file already exists" % c.path, n)
        elif current is None:
            rep.add("FAIL", "%s %s but file does not exist" % (c.action, c.path), n)
            continue
        if c.action == "MODIFY":
            read_chars += len(current or "")

        if c.action == "DELETE":
            if blocks:
                rep.add("FAIL", "DELETE %s must not have blocks" % c.path, n)
            tree.set(c.path, None)
            continue
        if c.mode == "FULL FILE":
            if len(blocks) != 1 or blocks[0].kind != "FULL":
                rep.add("FAIL", "%s (FULL FILE) needs exactly one FULL FILE block" % c.path, n)
                continue
        else:  # ANCHOR EDIT
            if not blocks or any(b.kind != "SEARCH" for b in blocks):
                rep.add("FAIL", "%s (ANCHOR EDIT) needs one or more SEARCH blocks only" % c.path, n)
                continue
        new, errs = mp.apply_blocks(current, blocks)
        for e in errs:
            rep.add("FAIL", e, n)
        tree.set(c.path, new)

    text = step_path.read_text(encoding="utf-8")
    # the model reads the step + files, then writes every FULL FILE / REPLACE text back out
    written_chars = sum(len(b.text) for b in step.blocks)
    tokens = mp.estimate_tokens(text) + mp.estimate_tokens("x" * (read_chars + written_chars))
    rep.add("INFO", "~%d tokens (budget %d)" % (tokens, mp.BUDGET), n)
    if tokens > mp.BUDGET:
        rep.add("FAIL", "over budget: ~%d tokens > %d, split this step" % (tokens, mp.BUDGET), n)
    elif tokens > mp.WARN_AT:
        rep.add("WARN", "near budget: ~%d tokens > %d" % (tokens, mp.WARN_AT), n)


def check_plan(plan_arg: str) -> int:
    rep = mp.Report()
    plan = Path(plan_arg).expanduser().resolve()
    if not plan.is_dir():
        rep.add("FAIL", "plan folder not found: %s" % plan)
        return rep.finish()
    meta = mp.read_meta(plan)
    if not meta:
        rep.add("FAIL", "meta file not found or empty in %s" % plan)
        return rep.finish()
    missing = [k for k in META_KEYS if not meta.get(k)]
    for k in missing:
        rep.add("FAIL", "meta: missing key %s" % k)
    if missing:
        return rep.finish()

    status = meta["status"]
    if status not in ("writing", "ready"):
        rep.add("FAIL", "meta: status must be writing or ready, got %r" % status)
    try:
        total = int(meta["steps"])
        if total < 1:
            raise ValueError
    except ValueError:
        rep.add("FAIL", "meta: steps must be a positive integer, got %r" % meta["steps"])
        return rep.finish()

    repo = Path(meta["repo"]).expanduser().resolve()
    if not _git_ok(repo, "rev-parse", "--show-toplevel"):
        rep.add("FAIL", "meta: repo is not a git repository: %s" % repo)
        return rep.finish()
    if _is_inside(plan, repo):
        rep.add("FAIL", "plan folder is inside the project repo (%s); move it outside" % repo)
    if not _git_ok(repo, "cat-file", "-e", meta["base"] + "^{commit}"):
        rep.add("FAIL", "meta: base commit %s not found in repo" % meta["base"])
        return rep.finish()

    if total > mp.MAX_STEPS:
        rep.add("WARN", "more than %d steps (%d): ask the user to split the task"
                % (mp.MAX_STEPS, total))

    found = {}
    for p in plan.iterdir():
        m = mp.STEP_FILE_RE.match(p.name)
        if m:
            found[int(m.group(1))] = p
    for k in sorted(found):
        if k < 1 or k > total:
            rep.add("FAIL", "unexpected step file %s (meta steps=%d)" % (found[k].name, total))
    if status == "ready":
        for k in range(1, total + 1):
            if k not in found:
                rep.add("FAIL", "step-%d.md missing" % k)
    else:
        rep.add("WARN", "plan incomplete (status=writing): %d of %d step files present"
                % (len([k for k in found if 1 <= k <= total]), total))

    rules = mp.rules_block(SKILL_DIR)
    tree = VirtualTree(repo, meta["base"])
    for k in range(1, total + 1):
        if k not in found:
            break  # simulation needs consecutive steps
        check_step(found[k], tree, rules, rep)
    return rep.finish()


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Validate a mandor plan folder.")
    ap.add_argument("plan_dir")
    args = ap.parse_args(argv)
    return check_plan(args.plan_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
