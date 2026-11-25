#!/usr/bin/env python3
"""PreToolUse hook for the mandor skill.

Blocks Claude from (1) writing files inside the project repo (Edit/Write tools and common Bash
writes: redirects, tee, cp, mv, rm, touch, mkdir, sed -i, adb pull, Gradle format/auto-correct
tasks) and (2) running git commands that change repository state. The project repo is the git repo
of the session's cwd, plus any git repo that is a Gradle project (so starting Claude outside the
repo does not switch the guard off). Commands inside `bash -c` / `sh -c` / `eval` are checked too.
Read-only git is allowed. This is a safety net for a well-meaning Claude, not a sandbox.

Reads the hook payload (JSON) from stdin. Exit 0 = allow, exit 2 = block (reason on stderr).
A malformed payload is allowed, so a broken hook never locks the session.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BLOCKED_GIT = {
    "commit", "push", "reset", "checkout", "switch", "rebase", "merge", "add", "rm", "mv",
    "restore", "clean", "cherry-pick", "revert", "am", "pull", "commit-tree", "update-ref",
    "filter-branch", "gc", "prune", "bisect", "update-index", "checkout-index", "read-tree",
    "fast-import", "replace",
}
# subcommand -> first arguments (or flags) that keep it read-only; anything else blocks
READ_ONLY_FORMS = {
    "stash": {"list", "show"},
    "tag": {"-l", "--list", "--contains", "--no-contains", "--points-at", "--merged",
            "--no-merged", "-n"},
    "worktree": {"list"},
    "apply": {"--check", "--stat", "--numstat", "--summary"},
    "config": {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin"},
    "remote": {"-v", "--verbose", "show", "get-url"},
    "notes": {"list", "show"},
    "submodule": {"status", "summary"},
    "reflog": {"show"},
}
BRANCH_MUTATING = {"-d", "-D", "-m", "-M", "-f", "-c", "-C", "--delete", "--move", "--force",
                   "--copy", "--set-upstream-to", "-u", "--unset-upstream", "--edit-description"}
BRANCH_LISTING = {"-a", "--all", "-r", "--remotes", "-l", "--list", "--show-current", "-v",
                  "-vv", "--verbose", "--contains", "--no-contains", "--merged", "--no-merged",
                  "--points-at", "--sort", "--format", "--column", "--no-column"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
WRAPPERS = {"sudo", "env", "command", "exec", "time", "nohup", "xargs", "nice", "timeout",
            "xcrun"}
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SHELL_C_RE = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
GRADLE_MARKERS = ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts")
MAX_DEPTH = 5
REDIRECT_RE = re.compile(r"^(\d*|&)?>>?(.*)$")
FILE_WRITERS_ALL_ARGS = {"tee", "rm", "rmdir", "touch", "mkdir", "truncate", "mv", "unlink"}
FILE_WRITERS_LAST_ARG = {"cp", "install", "ln", "rsync", "ditto"}
GRADLE_WRITE_TASK_RE = re.compile(r"(Format|Apply)$")
GRADLE_WRITE_FLAGS = {"--auto-correct", "-PautoCorrect=true", "--autocorrect"}

MSG_WRITE = ("mandor: Claude tidak boleh menulis file di repo project (%s). "
             "Tulis plan/bukti ke folder plan (path absolut) di luar repo.")
MSG_GIT = ("mandor: operasi git yang mengubah state (`git %s`) dikerjakan user, bukan Claude. "
           "Berikan command-nya ke user.")
MSG_GRADLE = ("mandor: task Gradle `%s` mengubah source di repo project. Pakai task cek saja "
              "(mis. ktlintCheck, detekt tanpa auto-correct, lint).")


def repo_root(cwd: str) -> Optional[Path]:
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    return Path(r.stdout.strip()).resolve()


def resolve(raw: str, cwd: str) -> Path:
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def protected_root(raw: str, cwd: str, cwd_root: Optional[Path]) -> Optional[Path]:
    """The project repo `raw` lies in, if writing there must be blocked."""
    p = resolve(raw, cwd)
    if cwd_root is not None and _inside(p, cwd_root):
        return cwd_root
    d = p
    while not d.is_dir() and d != d.parent:
        d = d.parent
    root = repo_root(str(d))
    if root is not None and any((root / m).is_file() for m in GRADLE_MARKERS):
        return root
    return None


def blocked_write(payload: dict) -> Optional[str]:
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    cwd = payload.get("cwd") or os.getcwd()
    root = protected_root(raw, cwd, repo_root(cwd))
    return MSG_WRITE % root if root is not None else None


def split_commands(cmd: str) -> List[str]:
    """Split a command line on shell operators outside quotes. Command substitutions ($(...) and
    backticks, also inside double quotes) and subshells become segments of their own."""
    segs: List[str] = []
    cur: List[str] = []
    stack: List[str] = []  # open contexts: ' " $( ` (
    i, n = 0, len(cmd)

    def cut() -> None:
        segs.append("".join(cur))
        del cur[:]

    while i < n:
        c = cmd[i]
        top = stack[-1] if stack else None
        if top == "'":
            cur.append(c)
            if c == "'":
                stack.pop()
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if cmd.startswith("$(", i):
            cut()
            stack.append("$(")
            i += 2
            continue
        if c == "`":
            cut()
            if top == "`":
                stack.pop()
            else:
                stack.append("`")
            i += 1
            continue
        if top == '"':
            cur.append(c)
            if c == '"':
                stack.pop()
            i += 1
            continue
        if c in "'\"":
            stack.append(c)
            cur.append(c)
        elif c == "(":
            cut()
            stack.append("(")
        elif c == ")":
            cut()
            if top in ("$(", "("):
                stack.pop()
        elif cmd.startswith("&&", i) or cmd.startswith("||", i):
            cut()
            i += 1
        elif c in ";|&\n":
            cut()
        else:
            cur.append(c)
        i += 1
    cut()
    return [seg for seg in segs if seg.strip()]


def _tokens(segment: str) -> List[str]:
    try:
        return shlex.split(segment)
    except ValueError:  # segment cut inside quotes by a substitution
        return [t.strip("'\"") for t in segment.split()]


def inner_script(tokens: List[str]) -> Optional[str]:
    """The command string run by `bash -c <script>`, `sh -lc <script>` or `eval <args>`."""
    cmd = _strip_wrappers(tokens)
    if not cmd:
        return None
    name = os.path.basename(cmd[0])
    if name == "eval":
        return " ".join(cmd[1:])
    if name in SHELLS:
        for j in range(1, len(cmd) - 1):
            if SHELL_C_RE.match(cmd[j]):
                return cmd[j + 1]
    return None


def _strip_wrappers(tokens: List[str]) -> List[str]:
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in WRAPPERS or ASSIGN_RE.match(t):
            i += 1
            continue
        if i > 0 and tokens[i - 1] in WRAPPERS and t.startswith("-"):
            i += 1  # wrapper option such as `env -i`, `nice -n`
            continue
        if i > 0 and tokens[i - 1] in ("timeout", "-n") and re.match(r"^\d+[smhd]?$", t):
            i += 1  # `timeout 60`, `nice -n 5`
            continue
        break
    return tokens[i:]


def git_subcommand(tokens: List[str]) -> Optional[List[str]]:
    """Return [subcommand, args...] if this segment runs git, else None."""
    tokens = _strip_wrappers(tokens)
    if not tokens or os.path.basename(tokens[0]) != "git":
        return None
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in GIT_OPTS_WITH_VALUE else 1
    if i >= len(tokens):
        return None
    return tokens[i:]


def git_reason(sub: List[str]) -> Optional[str]:
    name, args = sub[0], sub[1:]
    label = " ".join(sub[:3])
    if name in BLOCKED_GIT:
        return MSG_GIT % label
    if name in READ_ONLY_FORMS:
        if name == "reflog" and (not args or args[0] not in ("expire", "delete")):
            return None
        if name in ("config", "tag", "notes", "submodule", "remote", "stash", "worktree") \
                and not args:
            return None if name != "stash" else MSG_GIT % label  # bare `git stash` stashes
        if any(a.split("=")[0] in READ_ONLY_FORMS[name] for a in args[:1] + args):
            return None
        return MSG_GIT % label
    if name == "symbolic-ref" and len([a for a in args if not a.startswith("-")]) >= 2:
        return MSG_GIT % label
    if name == "branch":
        if any(a.split("=")[0] in BRANCH_MUTATING for a in args):
            return MSG_GIT % label
        listing = any(a.split("=")[0] in BRANCH_LISTING for a in args)
        if not listing and any(not a.startswith("-") for a in args):
            return MSG_GIT % label  # `git branch <new> [<start>]` creates a branch
    return None


def write_targets(tokens: List[str], cwd: str) -> List[str]:
    """Paths this command segment would write to (best effort)."""
    targets: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(tokens):
        m = REDIRECT_RE.match(tokens[i])
        if m and tokens[i] not in ("-", ">-"):
            tgt = m.group(2)
            if not tgt and i + 1 < len(tokens):
                tgt = tokens[i + 1]
                i += 1
            if tgt and not tgt.startswith("&"):
                targets.append(tgt)
            i += 1
            continue
        rest.append(tokens[i])
        i += 1
    cmd = _strip_wrappers(rest)
    if not cmd:
        return targets
    name = os.path.basename(cmd[0])
    args = [a for a in cmd[1:] if not a.startswith("-")]
    if name in FILE_WRITERS_ALL_ARGS:
        targets += args
    elif name in FILE_WRITERS_LAST_ARG and args:
        targets.append(args[-1])
    elif name in ("sed", "gsed") and any(a == "-i" or a.startswith("-i") or a == "--in-place"
                                         for a in cmd[1:]):
        files = [a for a in cmd[1:] if a and not a.startswith("-")]
        has_e = any(a in ("-e", "-f") for a in cmd[1:])
        targets += files if has_e else files[1:]
    elif name == "adb" and len(cmd) > 1 and cmd[1] == "pull":
        pull_args = [a for a in cmd[2:] if not a.startswith("-")]
        targets.append(pull_args[-1] if len(pull_args) >= 2 else ".")
    return targets


def gradle_reason(tokens: List[str]) -> Optional[str]:
    cmd = _strip_wrappers(tokens)
    if not cmd or os.path.basename(cmd[0]) not in ("gradlew", "gradle"):
        return None
    for a in cmd[1:]:
        if a in GRADLE_WRITE_FLAGS:
            return MSG_GRADLE % a
        if not a.startswith("-") and GRADLE_WRITE_TASK_RE.search(a.split(":")[-1]):
            return MSG_GRADLE % a
    return None


HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(cmd: str) -> str:
    """Drop heredoc bodies: they are data written somewhere, not commands."""
    lines = cmd.split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group(2) for m in HEREDOC_RE.finditer(line)]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1  # skip the delimiter line
    return "\n".join(out)


def check_command(cmd: str, cwd: str, cwd_root: Optional[Path], depth: int = 0) -> Optional[str]:
    for segment in split_commands(strip_heredocs(cmd)):
        tokens = _tokens(segment)
        script = inner_script(tokens)
        if script is not None and depth < MAX_DEPTH:
            reason = check_command(script, cwd, cwd_root, depth + 1)
            if reason:
                return reason
            continue
        sub = git_subcommand(tokens)
        if sub:
            reason = git_reason(sub)
            if reason:
                return reason
            continue
        reason = gradle_reason(tokens)
        if reason:
            return reason
        for t in write_targets(tokens, cwd):
            root = protected_root(t, cwd, cwd_root)
            if root is not None:
                return MSG_WRITE % root
    return None


def blocked_bash(payload: dict) -> Optional[str]:
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    return check_command(cmd, cwd, repo_root(cwd))


def is_blocked(payload: dict) -> Optional[str]:
    tool = payload.get("tool_name")
    if tool in WRITE_TOOLS:
        return blocked_write(payload)
    if tool == "Bash":
        return blocked_bash(payload)
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
    except ValueError:
        return 0
    reason = is_blocked(payload)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
