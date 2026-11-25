"""Regression tests for the deferred minors fixed after v1 (CRLF, BOM, path forms, non-ASCII paths,
test-line detector, status=ready on verify, guard `bash -c` / quoted parens / Gradle repo outside cwd).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import (commit_all, execute_step, full_block, git, make_plan, make_repo, real_rules,
                     run_script, search_block, step_text, write_files)
from test_check_plan import meta_for

import guard
import mandor_plan as mp

KT = "app/src/main/java/com/x/A.kt"
TEST_KT = "app/src/test/java/com/x/ATest.kt"


def modify_step(n, path, search, replace):
    return step_text(n, "Edit", ["- MODIFY %s (ANCHOR EDIT)" % path], None,
                     search_block(path, search, replace), rules=real_rules())


class ApplyBlocksLineEndingsTest(unittest.TestCase):
    def test_crlf_file_matches_lf_anchor_and_keeps_crlf(self):
        content = "package x\r\n\r\nfun a() = 1\r\nfun b() = 2\r\n"
        blocks = [mp.Block(KT, "SEARCH", "fun a() = 1\nfun b() = 2", "fun a() = 10\nfun b() = 20")]
        new, errs = mp.apply_blocks(content, blocks)
        self.assertEqual(errs, [])
        self.assertEqual(new, "package x\r\n\r\nfun a() = 10\r\nfun b() = 20\r\n")

    def test_full_file_on_crlf_file_keeps_crlf(self):
        new, errs = mp.apply_blocks("a\r\nb\r\n", [mp.Block(KT, "FULL", None, "x\ny\n")])
        self.assertEqual((new, errs), ("x\r\ny\r\n", []))

    def test_full_file_on_bom_file_keeps_bom(self):
        new, errs = mp.apply_blocks("﻿a\n", [mp.Block(KT, "FULL", None, "x\n")])
        self.assertEqual((new, errs), ("﻿x\n", []))

    def test_lf_file_unchanged_behaviour(self):
        new, errs = mp.apply_blocks("a\nb\n", [mp.Block(KT, "SEARCH", "a", "c")])
        self.assertEqual((new, errs), ("c\nb\n", []))


class CheckPlanCrlfAndPathsTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.sha = make_repo({KT: "package x\r\n\r\nfun a() = 1\r\n"})

    def run_plan(self, steps):
        plan = make_plan(meta_for(self.repo, self.sha, len(steps)), steps)
        return run_script("check_plan.py", plan)

    def test_crlf_repo_file_passes(self):
        step = modify_step(1, KT, "package x\n\nfun a() = 1", "package x\n\nfun a() = 2")
        rc, out = self.run_plan({1: step})
        self.assertEqual(rc, 0, out)

    def test_non_canonical_paths_fail(self):
        for bad in ("./" + KT, "app/../" + KT, "/abs/A.kt", "app//src/A.kt", "app\\A.kt"):
            step = step_text(1, "Create", ["- CREATE %s (FULL FILE)" % bad], None,
                             full_block(bad, "x\n"), rules=real_rules())
            rc, out = self.run_plan({1: step})
            self.assertEqual(rc, 1, bad)
            self.assertIn("path must be relative to the repo root", out, bad)

    def test_bad_read_path_fails(self):
        step = step_text(1, "Edit", ["- MODIFY %s (ANCHOR EDIT)" % KT], ["- ./%s:1-1" % KT],
                         search_block(KT, "fun a() = 1", "fun a() = 2"), rules=real_rules())
        rc, out = self.run_plan({1: step})
        self.assertEqual(rc, 1, out)
        self.assertIn("path must be relative to the repo root", out)


class CheckCommitsMinorTest(unittest.TestCase):
    def plan_for(self, repo, sha, steps, status="ready"):
        return make_plan(meta_for(repo, sha, len(steps), status), steps)

    def test_crlf_file_executed_exactly_passes(self):
        repo, sha = make_repo({KT: "fun a() = 1\r\nfun b() = 2\r\n"})
        steps = {1: modify_step(1, KT, "fun a() = 1\nfun b() = 2", "fun a() = 9\nfun b() = 2")}
        execute_step(repo, steps[1])
        rc, out = run_script("check_commits.py", self.plan_for(repo, sha, steps), "--repo", repo)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("WARN", out)

    def test_bom_dropped_by_editor_is_only_a_warning(self):
        repo, sha = make_repo({KT: "﻿fun a() = 1\n"})
        steps = {1: step_text(1, "Rewrite", ["- MODIFY %s (FULL FILE)" % KT], None,
                              full_block(KT, "fun a() = 2\n"), rules=real_rules())}
        write_files(repo, {KT: "fun a() = 2\n"})  # editor saved without the BOM
        commit_all(repo, "step")
        rc, out = run_script("check_commits.py", self.plan_for(repo, sha, steps), "--repo", repo)
        self.assertEqual(rc, 0, out)
        self.assertIn("formatting differs", out)

    def test_non_ascii_path_is_in_scope(self):
        path = "app/src/main/res/raw/café.txt"
        repo, sha = make_repo({path: "a\n"})
        steps = {1: modify_step(1, path, "a", "b")}
        execute_step(repo, steps[1])
        rc, out = run_script("check_commits.py", self.plan_for(repo, sha, steps), "--repo", repo)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("out-of-scope", out)

    def test_status_writing_fails(self):
        repo, sha = make_repo({KT: "fun a() = 1\n"})
        steps = {1: modify_step(1, KT, "fun a() = 1", "fun a() = 2")}
        execute_step(repo, steps[1])
        plan = self.plan_for(repo, sha, steps, status="writing")
        rc, out = run_script("check_commits.py", plan, "--repo", repo)
        self.assertEqual(rc, 1, out)
        self.assertIn("status=writing", out)

    def test_removed_assertions_of_common_android_test_libs_flagged(self):
        lines = [
            "        result shouldBe 3",
            "        result.shouldBeInstanceOf<Ok>()",
            "        verify { api.rate() }",
            "        coVerify(exactly = 1) { api.rate() }",
            "        verify(api).rate()",
            "        confirmVerified(api)",
            "        assertThat(result).isEqualTo(3)",
            "        expectThat(result).isEqualTo(3)",
            "        assertEquals(3, awaitItem())",
            "        awaitComplete()",
            "        expectNoEvents()",
            "        fail(\"boom\")",
        ]
        body = "class ATest {\n    @Test fun t() {\n%s\n    }\n}\n" % "\n".join(lines)
        repo, sha = make_repo({TEST_KT: body, KT: "fun a() = 1\n"})
        steps = {1: modify_step(1, KT, "fun a() = 1", "fun a() = 2")}
        stripped = "class ATest {\n    @Test fun t() {\n    }\n}\n"
        execute_step(repo, steps[1], mutate=lambda r: (r / TEST_KT).write_text(stripped))
        rc, out = run_script("check_commits.py", self.plan_for(repo, sha, steps), "--repo", repo)
        self.assertEqual(rc, 1, out)
        for line in lines:
            self.assertIn("test line removed in %s: %s" % (TEST_KT, line.strip()), out, line)


def bash(cmd, cwd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)}


class GuardMinorTest(unittest.TestCase):
    def setUp(self):
        self.repo, _ = make_repo({"app/A.kt": "a\n", "settings.gradle.kts": "\n"})
        self.outside = Path(tempfile.mkdtemp()).resolve()

    def test_shell_dash_c_is_inspected(self):
        for cmd in ('bash -c "git push"', "sh -c 'git commit -m x'", 'zsh -lc "git reset --hard"',
                    '/bin/bash -c "cd app; git push origin main"', 'eval "git push"',
                    "bash -c 'echo x > app/A.kt'"):
            self.assertIsNotNone(guard.is_blocked(bash(cmd, self.repo)), cmd)

    def test_shell_dash_c_read_only_allowed(self):
        for cmd in ('bash -c "git status && git log -1"', "sh -c 'ls app'"):
            self.assertIsNone(guard.is_blocked(bash(cmd, self.repo)), cmd)

    def test_parentheses_inside_quotes_do_not_split(self):
        src = self.outside / "a (1).kt"
        cmd = 'cp "%s" app/' % src
        self.assertIsNotNone(guard.is_blocked(bash(cmd, self.repo)), cmd)
        cmd = 'cp app/A.kt "%s"' % (self.outside / "out (1).kt")
        self.assertIsNone(guard.is_blocked(bash(cmd, self.repo)), cmd)

    def test_substitution_inside_double_quotes_still_checked(self):
        for cmd in ('echo "$(git push)"', 'echo "x `git commit -m y` z"'):
            self.assertIsNotNone(guard.is_blocked(bash(cmd, self.repo)), cmd)

    def test_gradle_repo_protected_when_claude_started_outside(self):
        target = self.repo / "app/A.kt"
        p = {"tool_name": "Edit", "tool_input": {"file_path": str(target)},
             "cwd": str(self.outside)}
        self.assertIsNotNone(guard.is_blocked(p))
        self.assertIsNotNone(guard.is_blocked(bash("echo x > %s" % target, self.outside)))
        self.assertIsNotNone(guard.is_blocked(bash("touch %s/app/New.kt" % self.repo,
                                                   self.outside)))

    def test_non_gradle_repo_outside_cwd_still_writable(self):
        notes, _ = make_repo({"notes.md": "x\n"})
        p = {"tool_name": "Write", "tool_input": {"file_path": str(notes / "plan/step-1.md")},
             "cwd": str(self.outside)}
        self.assertIsNone(guard.is_blocked(p))


if __name__ == "__main__":
    unittest.main()
