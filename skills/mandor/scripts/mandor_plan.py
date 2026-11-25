"""Shared parsing and simulation helpers for mandor plan folders.

Format contract: references/plan-format.md. Python 3.9+, stdlib only.
"""
from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SECTIONS = [
    "EXECUTOR RULES",
    "GOAL",
    "FILES TO CHANGE",
    "FILES TO READ",
    "CHANGES",
    "FORBIDDEN",
    "DONE WHEN",
]
BUDGET = 16000
WARN_AT = 12000
MAX_FILES_PER_STEP = 2
MAX_STEPS = 10

MARKER_RE = re.compile(r"^<!-- mandor step=(\d+) -->$")
TITLE_RE = re.compile(r"^# Step (\d+): (.+)$")
STEP_FILE_RE = re.compile(r"^step-(\d+)\.md$")
CHANGE_RE = re.compile(r"^- (CREATE|MODIFY) (\S+) \((FULL FILE|ANCHOR EDIT)\)$")
DELETE_RE = re.compile(r"^- DELETE (\S+)$")
READ_RE = re.compile(r"^- (\S+):(\d+)-(\d+)$")

OPEN_SEARCH = "<<<<<<< SEARCH"
OPEN_FULL = "<<<<<<< FULL FILE"
DIVIDER = "======="
CLOSE_REPLACE = ">>>>>>> REPLACE"
CLOSE_FULL = ">>>>>>> END"


@dataclass
class FileChange:
    action: str
    path: str
    mode: Optional[str]


@dataclass
class ReadRef:
    path: str
    start: int
    end: int


@dataclass
class Block:
    path: str
    kind: str  # "SEARCH" or "FULL"
    search: Optional[str]
    text: str


@dataclass
class Step:
    number: int
    title: str
    sections: Dict[str, str] = field(default_factory=dict)
    changes: List[FileChange] = field(default_factory=list)
    reads: List[ReadRef] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Report:
    """Collects INFO/WARN/FAIL lines and prints them with a final RESULT line."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.fails = 0

    def add(self, level: str, msg: str, step: Optional[int] = None) -> None:
        prefix = "step %d: " % step if step is not None else ""
        self.lines.append("%s %s%s" % (level, prefix, msg))
        if level == "FAIL":
            self.fails += 1

    def raw(self, line: str) -> None:
        self.lines.append("    " + line)

    def finish(self) -> int:
        for line in self.lines:
            print(line)
        if self.fails:
            print("RESULT: FAIL (%d failures)" % self.fails)
            return 1
        print("RESULT: PASS")
        return 0


def read_meta(plan_dir: Path) -> Dict[str, str]:
    p = Path(plan_dir) / "meta"
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def rules_block(skill_dir: Path) -> str:
    return (Path(skill_dir) / "references" / "executor-rules.md").read_text(encoding="utf-8").strip()


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def git_show(repo: Path, rev: str, path: str) -> Optional[str]:
    r = subprocess.run(["git", "-C", str(repo), "show", "%s:%s" % (rev, path)],
                       capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def _split_sections(lines: List[str], errors: List[str]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Split body lines into sections. Lines inside change blocks are never headers."""
    order: List[str] = []
    bodies: Dict[str, List[str]] = {}
    current = None
    in_block = False
    for line in lines:
        if not in_block and line.startswith("## "):
            current = line[3:].strip()
            if current in bodies:
                errors.append("duplicate section %s" % current)
            order.append(current)
            bodies[current] = []
            continue
        if current == "CHANGES":
            if line in (OPEN_SEARCH, OPEN_FULL):
                in_block = True
            elif line in (CLOSE_REPLACE, CLOSE_FULL):
                in_block = False
        if current is not None:
            bodies[current].append(line)
        elif line.strip():
            errors.append("text before first section: %r" % line[:60])
    return order, bodies


def _parse_blocks(lines: List[str], errors: List[str]) -> List[Block]:
    blocks: List[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not line.startswith("FILE: "):
            errors.append("unexpected text in CHANGES: %r" % line[:60])
            i += 1
            continue
        path = line[len("FILE: "):].strip()
        i += 1
        while i < n and not lines[i].strip():
            i += 1
        if i >= n or lines[i] not in (OPEN_SEARCH, OPEN_FULL):
            errors.append("FILE: %s is not followed by a SEARCH or FULL FILE block" % path)
            continue
        kind = "SEARCH" if lines[i] == OPEN_SEARCH else "FULL"
        i += 1
        first: List[str] = []
        second: List[str] = []
        target = first
        closed = False
        while i < n:
            cur = lines[i]
            i += 1
            if kind == "SEARCH" and cur == DIVIDER and target is first:
                target = second
                continue
            if (kind == "SEARCH" and cur == CLOSE_REPLACE and target is second) or \
                    (kind == "FULL" and cur == CLOSE_FULL):
                closed = True
                break
            target.append(cur)
        if not closed:
            errors.append("unterminated %s block for %s" % (kind, path))
            break
        if kind == "SEARCH":
            blocks.append(Block(path, "SEARCH", "\n".join(first), "\n".join(second)))
        else:
            blocks.append(Block(path, "FULL", None, "\n".join(first) + "\n"))
    return blocks


def parse_step(path: Path) -> Step:
    path = Path(path)
    errors: List[str] = []
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    m_file = STEP_FILE_RE.match(path.name)
    file_no = int(m_file.group(1)) if m_file else None
    if file_no is None:
        errors.append("file name %s is not step-<N>.md" % path.name)

    number = file_no or 0
    m = MARKER_RE.match(lines[idx].strip()) if idx < len(lines) else None
    if not m:
        errors.append("first line must be <!-- mandor step=N -->")
    else:
        number = int(m.group(1))
        if file_no is not None and number != file_no:
            errors.append("marker step=%d does not match file %s" % (number, path.name))
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    title = ""
    t = TITLE_RE.match(lines[idx].strip()) if idx < len(lines) else None
    if not t:
        errors.append("missing title line '# Step N: <title>'")
    else:
        title = t.group(2).strip()
        if int(t.group(1)) != number:
            errors.append("title step number %s does not match step %d" % (t.group(1), number))
        idx += 1

    order, bodies = _split_sections(lines[idx:], errors)
    for name in order:
        if name not in SECTIONS:
            errors.append("unknown section %s" % name)
    for name in SECTIONS:
        if name not in bodies:
            errors.append("missing section %s" % name)
    known = [s for s in order if s in SECTIONS]
    expected = [s for s in SECTIONS if s in known]
    if known != expected:
        errors.append("section order must be: %s" % ", ".join(SECTIONS))

    step = Step(number=number, title=title, errors=errors)
    step.sections = {k: "\n".join(v).strip("\n") for k, v in bodies.items()}

    for line in bodies.get("FILES TO CHANGE", []):
        s = line.strip()
        if not s:
            continue
        c = CHANGE_RE.match(s)
        d = DELETE_RE.match(s)
        if c:
            action, p, mode = c.groups()
            if action == "CREATE" and mode != "FULL FILE":
                errors.append("CREATE %s must use (FULL FILE)" % p)
            step.changes.append(FileChange(action, p, mode))
        elif d:
            step.changes.append(FileChange("DELETE", d.group(1), None))
        else:
            errors.append("invalid FILES TO CHANGE line: %r" % s)

    for line in bodies.get("FILES TO READ", []):
        s = line.strip()
        if not s or s == "- none":
            continue
        r = READ_RE.match(s)
        if r and 1 <= int(r.group(2)) <= int(r.group(3)):
            step.reads.append(ReadRef(r.group(1), int(r.group(2)), int(r.group(3))))
        else:
            errors.append("invalid FILES TO READ line: %r" % s)

    step.blocks = _parse_blocks(bodies.get("CHANGES", []), errors)
    return step


def apply_blocks(content: Optional[str], blocks: List[Block]) -> Tuple[Optional[str], List[str]]:
    errors: List[str] = []
    for b in blocks:
        if b.kind == "FULL":
            content = b.text
            continue
        if content is None:
            errors.append("SEARCH block on missing file %s" % b.path)
            continue
        count = content.count(b.search) if b.search else 0
        if count != 1:
            errors.append("SEARCH block not unique in %s (found %d)" % (b.path, count))
            continue
        content = content.replace(b.search, b.text, 1)
    return content, errors
