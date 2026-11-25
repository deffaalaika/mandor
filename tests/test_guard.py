from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo, run_script

import guard


def bash(cmd, cwd="/tmp"):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd}


class GuardWriteTest(unittest.TestCase):
    def setUp(self):
        self.repo, _ = make_repo({"app/A.kt": "a\n"})
        self.outside = Path(tempfile.mkdtemp())

    def payload(self, tool, path, cwd=None, key="file_path"):
        return {"tool_name": tool, "tool_input": {key: str(path)}, "cwd": str(cwd or self.repo)}

    def test_write_inside_repo_blocked(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            reason = guard.is_blocked(self.payload(tool, self.repo / "app/A.kt"))
            self.assertIsNotNone(reason, tool)
            self.assertIn("mandor:", reason)

    def test_new_file_inside_repo_blocked(self):
        self.assertIsNotNone(guard.is_blocked(self.payload("Write", self.repo / "new/B.kt")))

    def test_notebook_inside_repo_blocked(self):
        p = self.payload("NotebookEdit", self.repo / "n.ipynb", key="notebook_path")
        self.assertIsNotNone(guard.is_blocked(p))

    def test_write_outside_repo_allowed(self):
        self.assertIsNone(guard.is_blocked(self.payload("Write", self.outside / "step-1.md")))

    def test_relative_path_resolved_against_cwd(self):
        p = self.payload("Edit", "A.kt", cwd=self.repo / "app")
        self.assertIsNotNone(guard.is_blocked(p))
        p = self.payload("Write", "../plan/step-1.md", cwd=self.repo)
        self.assertIsNone(guard.is_blocked(p))

    def test_not_a_repo_allowed(self):
        p = self.payload("Write", self.outside / "x.md", cwd=self.outside)
        self.assertIsNone(guard.is_blocked(p))

    def test_read_tool_allowed(self):
        self.assertIsNone(guard.is_blocked(self.payload("Read", self.repo / "app/A.kt")))


class GuardBashTest(unittest.TestCase):
    BLOCKED = [
        "git commit -m x",
        "cd app && git push",
        "git -C /tmp/r reset --hard HEAD~1",
        'git -C "/tmp/my repo" checkout main',
        "git -c user.name=x commit -m y",
        "FOO=1 git stash",
        "git branch -D old",
        "git add -A",
        "git rebase main",
        "git merge side",
        "git restore app/A.kt",
        "git clean -fdx",
        "git cherry-pick abc",
        "git pull",
        "git switch -c x",
        "ls; git tag v1",
        "sudo git push",
        "/usr/bin/git commit",
        "git status | cat && git commit -am x",
        "git branch mandor-backup-rev1 HEAD",
        "git bisect start",
        "git config user.email x@y",
        "git remote add origin x",
        "git update-index --assume-unchanged a",
        "git notes add -m x",
        "git reflog expire --all",
        "git submodule update",
        "git read-tree HEAD",
        "git checkout-index -a",
    ]
    ALLOWED = [
        "git status",
        "git log --oneline abc..HEAD",
        "git diff HEAD~1",
        "git show abc:file.kt",
        "git rev-parse HEAD",
        "git -C /tmp/r log -1",
        "git branch --show-current",
        "git branch -a",
        "git merge-base --is-ancestor a HEAD",
        "git diff-tree -r --name-status abc",
        "./gradlew :app:testDebugUnitTest",
        "adb logcat -d",
        'echo "git commit"',
        "python3 check_commits.py /p --repo .",
        "git config --get user.email",
        "git config --list",
        "git remote -v",
        "git reflog show -5",
        "git submodule status",
    ]

    def test_blocked(self):
        for cmd in self.BLOCKED:
            reason = guard.is_blocked(bash(cmd))
            self.assertIsNotNone(reason, cmd)
            self.assertIn("mandor:", reason)

    def test_allowed(self):
        for cmd in self.ALLOWED:
            self.assertIsNone(guard.is_blocked(bash(cmd)), cmd)


class GuardBashWriteTest(unittest.TestCase):
    def setUp(self):
        self.repo, _ = make_repo({"app/A.kt": "a\n"})
        self.outside = Path(tempfile.mkdtemp())

    def blocked(self, cmd):
        return guard.is_blocked(bash(cmd, cwd=str(self.repo)))

    def test_redirect_into_repo_blocked(self):
        self.assertIsNotNone(self.blocked("adb exec-out screencap -p > shot.png"))
        self.assertIsNotNone(self.blocked("echo x >>app/A.kt"))

    def test_redirect_outside_allowed(self):
        self.assertIsNone(self.blocked("adb exec-out screencap -p > %s/shot.png" % self.outside))
        self.assertIsNone(self.blocked("./gradlew :app:testDebugUnitTest 2>/dev/null"))
        self.assertIsNone(self.blocked("./gradlew :app:lint > %s/lint.txt 2>&1" % self.outside))

    def test_file_commands_into_repo_blocked(self):
        for cmd in ("tee app/x.txt", "cp /tmp/a app/A.kt", "mv app/A.kt app/B.kt", "rm app/A.kt",
                    "touch app/N.kt", "sed -i '' 's/a/b/' app/A.kt", "adb pull /sdcard/dump.xml",
                    "adb pull /sdcard/dump.xml app/"):
            self.assertIsNotNone(self.blocked(cmd), cmd)

    def test_file_commands_outside_allowed(self):
        o = self.outside
        for cmd in ("cp %s/a %s/b" % (o, o), "sed -i '' 's/a/b/' %s/meta" % o,
                    "adb pull /sdcard/dump.xml %s/evidence/" % o, "mkdir -p %s/evidence" % o,
                    "cat app/A.kt", "rm -f %s/x" % o):
            self.assertIsNone(self.blocked(cmd), cmd)

    def test_heredoc_body_is_not_parsed(self):
        o = self.outside
        cmd = ("cat > %s/step-1.md <<'EOF'\nval ok = a > b && c\ngit reset --hard\nEOF\n" % o)
        self.assertIsNone(self.blocked(cmd))
        cmd2 = "cat > app/A.kt <<EOF\nx\nEOF"
        self.assertIsNotNone(self.blocked(cmd2))

    def test_gradle_format_tasks_blocked(self):
        for cmd in ("./gradlew ktlintFormat", "./gradlew :app:spotlessApply",
                    "./gradlew detekt --auto-correct"):
            self.assertIsNotNone(self.blocked(cmd), cmd)
        self.assertIsNone(self.blocked("./gradlew ktlintCheck detekt"))


class GuardCliTest(unittest.TestCase):
    def test_block_exit_code_2(self):
        code, out = run_script("guard.py", stdin=json.dumps(bash("git push")))
        self.assertEqual(code, 2)
        self.assertIn("mandor:", out)

    def test_allow_exit_code_0(self):
        code, _ = run_script("guard.py", stdin=json.dumps(bash("git status")))
        self.assertEqual(code, 0)

    def test_malformed_json_allows(self):
        code, _ = run_script("guard.py", stdin="{")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
