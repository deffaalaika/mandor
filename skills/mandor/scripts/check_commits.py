#!/usr/bin/env python3
"""Check the commits made by the local model against a mandor plan.

Commit N (in order, after meta.base) must be the exact result of applying step N.

Usage: check_commits.py <plan-dir> [--repo <path>]   (default --repo: current directory)
Exit: 0 = PASS, 1 = FAIL, 2 = usage error.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.dont_write_bytecode = True  # keep the installed skill folder clean
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mandor_plan as mp  # noqa: E402

META_KEYS = ["repo", "base", "steps"]
SUSPICIOUS_RE = re.compile(r"@Ignore|@Disabled|\bTODO\b|FIXME|NotImplementedError|!!")
TEST_LINE_RE = re.compile(r"@Test|assert")
MAX_DIFF_LINES = 20
EXPECTED_STATUS = {"CREATE": "A", "MODIFY": "M", "DELETE": "D"}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def toplevel(path: Path) -> Optional[Path]:
    r = git(path, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        return None
    return Path(r.stdout.strip()).resolve()


def normalize(text: Optional[str]) -> str:
    if text is None:
        return ""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).rstrip("\n")


def changed_files(repo: Path, sha: str) -> Dict[str, str]:
    r = git(repo, "diff-tree", "-r", "--no-commit-id", "--name-status", "-M", sha)
    out: Dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0][0]
        if status == "R" and len(parts) == 3:
            out[parts[1]] = "D"
            out[parts[2]] = "A"
        elif len(parts) >= 2:
            out[parts[1]] = status
    return out


def is_test_path(path: str) -> bool:
    return "/test/" in path or "/androidTest/" in path or path.startswith(("test/", "androidTest/"))


def report_deviation(rep: mp.Report, n: int, path: str, expected: str, actual: str) -> None:
    rep.add("FAIL", "content deviates from plan: %s" % path, n)
    exp_lines = normalize(expected).split("\n")
    act_lines = normalize(actual).split("\n")
    diff = list(difflib.unified_diff(exp_lines, act_lines, "plan", "commit", lineterm="", n=1))
    for line in diff[:MAX_DIFF_LINES]:
        rep.raw(line)
    if len(diff) > MAX_DIFF_LINES:
        rep.raw("... (%d more diff lines)" % (len(diff) - MAX_DIFF_LINES))
    scan_diff(rep, n, path, diff)


def scan_diff(rep: mp.Report, n: int, path: str, diff: List[str]) -> None:
    """Flag cheating patterns in a unified diff (old -> new)."""
    for line in diff:
        if line.startswith("+") and not line.startswith("+++") and SUSPICIOUS_RE.search(line):
            rep.add("FAIL", "suspicious line added in %s: %s" % (path, line[1:].strip()), n)
        if line.startswith("-") and not line.startswith("---") and is_test_path(path) \
                and TEST_LINE_RE.search(line):
            rep.add("FAIL", "test line removed in %s: %s" % (path, line[1:].strip()), n)


def scan_commit_file(repo: Path, sha: str, path: str, rep: mp.Report, n: int) -> None:
    old = normalize(mp.git_show(repo, sha + "^", path)).split("\n")
    new = normalize(mp.git_show(repo, sha, path)).split("\n")
    scan_diff(rep, n, path, list(difflib.unified_diff(old, new, lineterm="", n=0)))


def check_pair(repo: Path, sha: str, step_path: Path, rep: mp.Report) -> None:
    step = mp.parse_step(step_path)
    n = step.number
    if step.errors:
        rep.add("FAIL", "plan step is invalid (run check_plan.py): %s" % "; ".join(step.errors), n)
        return
    rep.add("INFO", "commit %s <-> %s" % (sha[:9], step_path.name), n)
    changed = changed_files(repo, sha)
    listed = {c.path: c for c in step.changes}

    for path in sorted(changed):
        if path not in listed:
            rep.add("FAIL", "out-of-scope file %s (status %s)" % (path, changed[path]), n)
            scan_commit_file(repo, sha, path, rep, n)

    for path, c in listed.items():
        if path not in changed:
            rep.add("FAIL", "planned file not changed: %s" % path, n)
            continue
        if c.action == "DELETE":
            if changed[path] != "D":
                rep.add("FAIL", "%s planned as DELETE but commit status is %s"
                        % (path, changed[path]), n)
                scan_commit_file(repo, sha, path, rep, n)
            continue
        if changed[path] != EXPECTED_STATUS[c.action]:
            rep.add("WARN", "%s planned as %s but commit status is %s"
                    % (path, c.action, changed[path]), n)
        parent = mp.git_show(repo, sha + "^", path)
        expected, errs = mp.apply_blocks(parent, [b for b in step.blocks if b.path == path])
        if errs:
            rep.add("FAIL", "plan cannot be applied to parent commit: %s" % "; ".join(errs), n)
            continue
        actual = mp.git_show(repo, sha, path)
        if actual == expected:
            continue
        if normalize(actual) == normalize(expected):
            rep.add("WARN", "formatting differs from plan: %s" % path, n)
            continue
        report_deviation(rep, n, path, expected or "", actual or "")


def check_commits(plan_arg: str, repo_arg: str) -> int:
    rep = mp.Report()
    plan = Path(plan_arg).expanduser().resolve()
    meta = mp.read_meta(plan)
    if not meta:
        rep.add("FAIL", "meta file not found or empty in %s" % plan)
        return rep.finish()
    missing = [k for k in META_KEYS if not meta.get(k)]
    for k in missing:
        rep.add("FAIL", "meta: missing key %s" % k)
    if missing:
        return rep.finish()
    try:
        total = int(meta["steps"])
    except ValueError:
        rep.add("FAIL", "meta: steps must be an integer, got %r" % meta["steps"])
        return rep.finish()

    repo = toplevel(Path(repo_arg).expanduser())
    meta_repo = toplevel(Path(meta["repo"]).expanduser())
    if repo is None:
        rep.add("FAIL", "not a git repository: %s" % repo_arg)
        return rep.finish()
    if meta_repo != repo:
        rep.add("FAIL", "repo mismatch: plan is for %s, checking %s" % (meta["repo"], repo))
        return rep.finish()

    base = meta["base"]
    if git(repo, "merge-base", "--is-ancestor", base, "HEAD").returncode != 0:
        rep.add("FAIL", "base is not an ancestor of HEAD (rebase/merge/reset?): base %s" % base[:9])
        return rep.finish()

    merges = git(repo, "rev-list", "--merges", "%s..HEAD" % base).stdout.split()
    for m in merges:
        rep.add("FAIL", "merge commit %s after base; plan runs must be linear" % m[:9])
    branch = git(repo, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    # --exclude patterns apply to the next --branches/--remotes only, without the refs/... prefix
    own_args = ["rev-list", "%s..HEAD" % base, "--not"]
    own_args += (["--exclude=%s" % branch] if branch else []) + ["--branches"]
    own_args += (["--exclude=*/%s" % branch] if branch else []) + ["--remotes"]
    own = git(repo, *own_args).stdout.split()
    every = git(repo, "rev-list", "%s..HEAD" % base).stdout.split()
    if len(own) < len(every):
        rep.add("FAIL", "commits from another branch after base (pull/rebase/merge from main?): "
                "%d of %d commits after base are also on other branches"
                % (len(every) - len(own), len(every)))
        return rep.finish()
    commits = git(repo, "rev-list", "--reverse", "--no-merges", "%s..HEAD" % base).stdout.split()
    if len(commits) != total:
        rep.add("FAIL", "expected %d commits (one per step), found %d" % (total, len(commits)))

    for i, sha in enumerate(commits[:total], start=1):
        step_path = plan / ("step-%d.md" % i)
        if not step_path.is_file():
            rep.add("FAIL", "step-%d.md missing in plan folder" % i)
            continue
        check_pair(repo, sha, step_path, rep)

    if git(repo, "status", "--porcelain").stdout.strip():
        rep.add("WARN", "uncommitted changes in working tree")
    return rep.finish()


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Check commits against a mandor plan.")
    ap.add_argument("plan_dir")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    return check_commits(args.plan_dir, args.repo)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
