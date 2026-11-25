from __future__ import annotations

import unittest
from pathlib import Path

from helpers import (commit_all, execute_step, git, make_plan, make_repo, real_rules, run_script,
                     search_block, step_text, write_files)
from test_check_plan import BASE_FILES, NEW_FILE, REPO_FILE, meta_for, step1, step2

TEST_FILE = "app/src/test/java/com/x/valas/ValasRepositoryTest.kt"
TEST_BASE = (
    "class ValasRepositoryTest {\n"
    "    @Test fun rateIsPositive() {\n"
    "        assertTrue(repo.rate() > 0)\n"
    "    }\n"
    "}\n"
)


def rewrite(path, fn):
    def mutate(repo: Path):
        p = repo / path
        p.write_bytes(fn(p.read_text(encoding="utf-8")).encode("utf-8"))
    return mutate


class CheckCommitsTest(unittest.TestCase):
    def setUp(self):
        files = dict(BASE_FILES)
        files[TEST_FILE] = TEST_BASE
        self.repo, self.sha = make_repo(files)
        self.steps = {1: step1(), 2: step2()}
        self.plan = make_plan(meta_for(self.repo, self.sha, 2), self.steps)

    def check(self, repo=None, cwd=None):
        args = [self.plan] if cwd else [self.plan, "--repo", repo or self.repo]
        return run_script("check_commits.py", *args, cwd=cwd)

    def run_all(self, mutate2=None):
        execute_step(self.repo, self.steps[1])
        execute_step(self.repo, self.steps[2], mutate=mutate2)

    def assertPass(self, res):
        self.assertEqual(res[0], 0, res[1])
        self.assertIn("RESULT: PASS", res[1])

    def assertFail(self, res, *needles):
        self.assertEqual(res[0], 1, res[1])
        for n in needles:
            self.assertIn(n, res[1])

    def test_exact_execution_passes(self):
        self.run_all()
        res = self.check()
        self.assertPass(res)
        self.assertNotIn("WARN", res[1])

    def test_default_repo_is_cwd(self):
        self.run_all()
        self.assertPass(self.check(cwd=str(self.repo / "app")))

    def test_commit_count_mismatch_fails(self):
        execute_step(self.repo, self.steps[1])
        self.assertFail(self.check(), "expected 2 commits", "found 1")

    def test_out_of_scope_file_fails(self):
        self.run_all(mutate2=lambda r: write_files(r, {"build.gradle.kts": "// new dep\n"}))
        self.assertFail(self.check(), "step 2:", "out-of-scope file build.gradle.kts")

    def test_cheat_in_out_of_scope_test_file_flagged(self):
        self.run_all(mutate2=rewrite(TEST_FILE, lambda t: t.replace(
            "    @Test fun", "    @Ignore\n    @Test fun").replace(
            "        assertTrue(repo.rate() > 0)\n", "")))
        self.assertFail(self.check(), "out-of-scope file %s" % TEST_FILE,
                        "suspicious line added in %s: @Ignore" % TEST_FILE,
                        "test line removed in %s: assertTrue" % TEST_FILE)

    def test_planned_file_untouched_fails(self):
        execute_step(self.repo, self.steps[1])
        # executor only changes NEW_FILE, forgets REPO_FILE
        write_files(self.repo, {NEW_FILE: "package com.x.valas\n\nsealed class RateResult {\n"
                                          "    object Error : RateResult()\n}\n"})
        commit_all(self.repo)
        self.assertFail(self.check(), "planned file not changed: %s" % REPO_FILE)

    def test_content_deviation_fails_with_diff(self):
        self.run_all(mutate2=rewrite(REPO_FILE, lambda t: t.replace("Double? = api.rate()",
                                                                    "Double? = api.rate() ?: 0.0")))
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("step 2: content deviates from plan: %s" % REPO_FILE, out)
        self.assertIn("    -", out)
        self.assertIn("    +", out)

    def test_whitespace_only_warns(self):
        self.run_all(mutate2=rewrite(REPO_FILE, lambda t: t.replace("\n", "  \r\n")))
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("WARN step 2: formatting differs from plan: %s" % REPO_FILE, out)

    def test_cheat_ignore_flagged(self):
        self.run_all(mutate2=rewrite(NEW_FILE, lambda t: t.replace("    object Error",
                                                                   "    @Ignore\n    object Error")))
        self.assertFail(self.check(), "suspicious line added", "@Ignore")

    def test_removed_assert_flagged(self):
        s = step_text(1, "Add test", ["- MODIFY %s (ANCHOR EDIT)" % TEST_FILE], None,
                      search_block(TEST_FILE, "        assertTrue(repo.rate() > 0)\n    }",
                                   "        assertTrue(repo.rate() > 0)\n    }\n\n"
                                   "    @Test fun rateNull() {\n        assertNull(repo.rate())\n    }"),
                      rules=real_rules())
        plan = make_plan(meta_for(self.repo, self.sha, 1), {1: s})
        execute_step(self.repo, s, mutate=rewrite(TEST_FILE, lambda t: t.replace(
            "        assertTrue(repo.rate() > 0)\n", "")))
        res = run_script("check_commits.py", plan, "--repo", self.repo)
        self.assertFail(res, "test line removed", "assertTrue")

    def test_plan_cannot_apply_to_parent(self):
        # step-1 commit also rewrites REPO_FILE, so the step-2 anchor is gone from its parent
        execute_step(self.repo, self.steps[1],
                     mutate=lambda r: write_files(r, {REPO_FILE: "package com.x.valas\n"}))
        write_files(self.repo, {NEW_FILE: "package com.x.valas\n// x\n",
                                REPO_FILE: "package com.x.valas\n// edited\n"})
        commit_all(self.repo)
        self.assertFail(self.check(), "out-of-scope file %s" % REPO_FILE,
                        "plan cannot be applied to parent commit")

    def test_base_not_ancestor_fails(self):
        self.run_all()
        git(self.repo, "checkout", "-q", "--orphan", "other")
        commit_all(self.repo, "orphan")
        self.assertFail(self.check(), "base is not an ancestor of HEAD")

    def test_merge_commit_fails(self):
        main = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "side")
        write_files(self.repo, {"side.txt": "x\n"})
        commit_all(self.repo, "side")
        git(self.repo, "checkout", "-q", main)
        execute_step(self.repo, self.steps[1])
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
        self.assertFail(self.check(), "merge commit")

    def test_rebase_onto_updated_main_fails(self):
        main = git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "feature")
        git(self.repo, "checkout", "-q", main)
        write_files(self.repo, {"app/B.kt": "teammate\n"})
        commit_all(self.repo, "teammate change on main")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", main)
        self.run_all()
        self.assertFail(self.check(), "commits from another branch after base")

    def test_own_pushed_branch_is_not_foreign(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.run_all()
        git(self.repo, "update-ref", "refs/remotes/origin/feature", "HEAD")
        self.assertPass(self.check())

    def test_planned_delete_but_modified_fails(self):
        write_files(self.repo, {"app/Old.kt": "class Old\n"})
        base = commit_all(self.repo, "add old")
        s = step_text(1, "Remove Old", ["- DELETE app/Old.kt"], None, "", rules=real_rules())
        plan = make_plan(meta_for(self.repo, base, 1), {1: s})
        write_files(self.repo, {"app/Old.kt": "// class Old\n// TODO remove\n"})
        commit_all(self.repo, "junior")
        res = run_script("check_commits.py", plan, "--repo", self.repo)
        self.assertFail(res, "planned as DELETE but commit status is M", "suspicious line added")

    def test_repo_mismatch_fails(self):
        other, _ = make_repo({"a.txt": "a\n"})
        self.assertFail(self.check(repo=other), "repo mismatch")

    def test_dirty_tree_warns(self):
        self.run_all()
        write_files(self.repo, {"scratch.txt": "x\n"})
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("WARN uncommitted changes in working tree", out)

    def test_missing_meta_fails(self):
        (self.plan / "meta").unlink()
        self.assertFail(self.check(), "meta")


if __name__ == "__main__":
    unittest.main()
