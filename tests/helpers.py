"""Shared test helpers: temp git repos, temp plan folders, step text builder."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "mandor"
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SECTION_ORDER = [
    "EXECUTOR RULES",
    "GOAL",
    "FILES TO CHANGE",
    "FILES TO READ",
    "CHANGES",
    "FORBIDDEN",
    "DONE WHEN",
]


def real_rules() -> str:
    return (SKILL_DIR / "references" / "executor-rules.md").read_text(encoding="utf-8").strip()


def step_text(n, title="Do thing", changes=None, reads=None, blocks="", rules="RULES",
              sections=None, order=None, marker=None) -> str:
    """Build a step file. `sections` overrides bodies, `order` overrides section order."""
    body = {
        "EXECUTOR RULES": rules,
        "GOAL": "Make the thing work.",
        "FILES TO CHANGE": "\n".join(changes or []),
        "FILES TO READ": "\n".join(reads or ["- none"]),
        "CHANGES": blocks.strip("\n"),
        "FORBIDDEN": "- Nothing else.",
        "DONE WHEN": "- File exists.",
    }
    if sections:
        body.update(sections)
    parts = ["<!-- mandor step=%s -->" % (marker if marker is not None else n),
             "# Step %d: %s" % (n, title), ""]
    for name in (order or SECTION_ORDER):
        parts += ["## " + name, body[name], ""]
    return "\n".join(parts)


def search_block(path, search, replace) -> str:
    return "FILE: %s\n<<<<<<< SEARCH\n%s\n=======\n%s\n>>>>>>> REPLACE\n" % (path, search, replace)


def full_block(path, text) -> str:
    return "FILE: %s\n<<<<<<< FULL FILE\n%s\n>>>>>>> END\n" % (path, text.rstrip("\n"))


def git(repo, *args, check=True) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True,
                       encoding="utf-8", env=env)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (args, r.stderr))
    return r.stdout.strip()


def write_files(repo, files: dict) -> None:
    for rel, text in files.items():
        p = Path(repo) / rel
        if text is None:
            if p.exists():
                p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))


def commit_all(repo, msg="c") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(files: dict, parent=None) -> tuple:
    """Create a git repo with one commit. Returns (repo_path, sha)."""
    repo = Path(tempfile.mkdtemp(prefix="mandor-repo-", dir=parent)).resolve()
    git(repo, "init", "-q")
    git(repo, "config", "core.autocrlf", "false")  # store bytes as written, whatever the host config
    write_files(repo, files)
    return repo, commit_all(repo, "base")


def make_plan(meta: dict, steps: dict, parent=None, name=None) -> Path:
    if name:
        base = Path(parent or tempfile.mkdtemp(prefix="mandor-plans-"))
        plan = base / name
        plan.mkdir(parents=True)
    else:
        plan = Path(tempfile.mkdtemp(prefix="mandor-plan-", dir=parent))
    (plan / "meta").write_text("".join("%s=%s\n" % kv for kv in meta.items()), encoding="utf-8")
    for n, text in steps.items():
        (plan / ("step-%d.md" % n)).write_text(text, encoding="utf-8")
    return plan


def run_script(name, *args, env=None, cwd=None, stdin=None) -> tuple:
    r = subprocess.run([sys.executable, str(SCRIPTS / name)] + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8", cwd=cwd, input=stdin,
                       env=dict(os.environ, **(env or {})))
    return r.returncode, r.stdout + r.stderr


def execute_step(repo, step_file_text: str, mutate=None, msg="step") -> str:
    """Apply a step exactly like an obedient executor would, optionally mutate, then commit."""
    import mandor_plan as mp
    d = Path(tempfile.mkdtemp())
    n = int(step_file_text.split("step=", 1)[1].split(" ", 1)[0])
    p = d / ("step-%d.md" % n)
    p.write_text(step_file_text, encoding="utf-8")
    step = mp.parse_step(p)
    assert not step.errors, step.errors
    for c in step.changes:
        target = Path(repo) / c.path
        if c.action == "DELETE":
            target.unlink()
            continue
        current = target.read_bytes().decode("utf-8") if target.exists() else None
        new, errs = mp.apply_blocks(current, [b for b in step.blocks if b.path == c.path])
        assert not errs, errs
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new.encode("utf-8"))
    if mutate:
        mutate(Path(repo))
    return commit_all(repo, msg)
