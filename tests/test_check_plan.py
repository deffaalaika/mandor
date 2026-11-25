from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import (full_block, make_plan, make_repo, real_rules, run_script, search_block,
                     step_text)

BASE_FILES = {
    "app/src/main/java/com/x/valas/ValasRepository.kt":
        "package com.x.valas\n\nclass ValasRepository {\n    fun rate(): Double = api.rate()!!\n}\n",
    "app/src/main/java/com/x/valas/ValasApi.kt":
        "package com.x.valas\n\ninterface ValasApi {\n    fun rate(): Double?\n}\n",
}
REPO_FILE = "app/src/main/java/com/x/valas/ValasRepository.kt"
NEW_FILE = "app/src/main/java/com/x/valas/RateResult.kt"


def meta_for(repo, sha, steps, status="ready"):
    return {"repo": str(repo), "base": sha, "steps": steps, "revision": 1, "status": status,
            "created": "2026-11-24", "task": "fix valas crash"}


def step1():
    return step_text(1, "Add RateResult", ["- CREATE %s (FULL FILE)" % NEW_FILE],
                     ["- app/src/main/java/com/x/valas/ValasApi.kt:1-5"],
                     full_block(NEW_FILE, "package com.x.valas\n\nsealed class RateResult\n"),
                     rules=real_rules())


def step2():
    # anchor exists only after step 1 created the file
    blocks = search_block(NEW_FILE, "sealed class RateResult",
                          "sealed class RateResult {\n    object Error : RateResult()\n}") + "\n" + \
        search_block(REPO_FILE, "    fun rate(): Double = api.rate()!!",
                     "    fun rate(): Double? = api.rate()")
    return step_text(2, "Use RateResult",
                     ["- MODIFY %s (ANCHOR EDIT)" % NEW_FILE, "- MODIFY %s (ANCHOR EDIT)" % REPO_FILE],
                     None, blocks, rules=real_rules())


class CheckPlanTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.sha = make_repo(BASE_FILES)

    def run_plan(self, steps, status="ready", n=None, **kw):
        plan = make_plan(meta_for(self.repo, self.sha, n or len(steps), status), steps, **kw)
        return plan, run_script("check_plan.py", plan)

    def assertPass(self, res):
        code, out = res
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: PASS", out)

    def assertFail(self, res, *needles):
        code, out = res
        self.assertEqual(code, 1, out)
        self.assertIn("RESULT: FAIL", out)
        for n in needles:
            self.assertIn(n, out)

    def test_valid_plan_passes(self):
        _, res = self.run_plan({1: step1(), 2: step2()})
        self.assertPass(res)
        self.assertIn("INFO step 1: ~", res[1])

    def test_anchor_against_previous_step_result(self):
        # same as valid plan; the anchor in step 2 only exists after step 1
        _, res = self.run_plan({1: step1(), 2: step2()})
        self.assertNotIn("found 0", res[1])

    def test_missing_meta_fails(self):
        plan = Path(tempfile.mkdtemp())
        self.assertFail(run_script("check_plan.py", plan), "meta")

    def test_missing_meta_key_fails(self):
        m = meta_for(self.repo, self.sha, 1)
        del m["base"]
        plan = make_plan(m, {1: step1()})
        self.assertFail(run_script("check_plan.py", plan), "missing key base")

    def test_bad_base_fails(self):
        m = meta_for(self.repo, "deadbeef" * 5, 1)
        plan = make_plan(m, {1: step1()})
        self.assertFail(run_script("check_plan.py", plan), "base")

    def test_plan_inside_repo_fails(self):
        _, res = self.run_plan({1: step1()}, parent=str(self.repo))
        self.assertFail(res, "plan folder is inside the project repo")

    def test_plan_dir_with_space_and_tilde(self):
        home = Path(tempfile.mkdtemp())
        plan = make_plan(meta_for(self.repo, self.sha, 1), {1: step1()}, parent=str(home),
                         name="my plans/valas")
        self.assertTrue(plan.is_dir())
        self.assertPass(run_script("check_plan.py", "~/my plans/valas", env={"HOME": str(home)}))

    def test_missing_step_file_when_ready(self):
        _, res = self.run_plan({1: step1()}, n=2)
        self.assertFail(res, "step-2.md missing")

    def test_extra_step_file_fails(self):
        _, res = self.run_plan({1: step1(), 2: step2()}, n=1)
        self.assertFail(res, "unexpected step file step-2.md")

    def test_status_writing_warns_only(self):
        _, res = self.run_plan({1: step1()}, status="writing", n=3)
        self.assertPass(res)
        self.assertIn("WARN", res[1])
        self.assertIn("plan incomplete", res[1])

    def test_bad_status_fails(self):
        _, res = self.run_plan({1: step1()}, status="done")
        self.assertFail(res, "status")

    def test_modified_rules_block_fails(self):
        s = step1().replace("Do ONLY this step.", "Do this step.")
        _, res = self.run_plan({1: s})
        self.assertFail(res, "step 1: executor rules block modified")

    def test_parse_error_reported(self):
        s = step1().replace("## FORBIDDEN", "## NOPE")
        _, res = self.run_plan({1: s})
        self.assertFail(res, "step 1: missing section FORBIDDEN")

    def test_three_files_fails(self):
        s = step_text(1, "x", ["- CREATE a.kt (FULL FILE)", "- CREATE b.kt (FULL FILE)",
                               "- CREATE c.kt (FULL FILE)"], None,
                      full_block("a.kt", "a") + full_block("b.kt", "b") + full_block("c.kt", "c"),
                      rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "more than 2 files")

    def test_empty_files_to_change_fails(self):
        s = step_text(1, "x", [], None, "", rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "FILES TO CHANGE is empty")

    def test_block_for_unlisted_file_fails(self):
        s = step_text(1, "x", ["- CREATE a.kt (FULL FILE)"], None,
                      full_block("a.kt", "a") + full_block("b.kt", "b"), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "block for unlisted file b.kt")

    def test_anchor_edit_needs_search_block(self):
        s = step_text(1, "x", ["- MODIFY %s (ANCHOR EDIT)" % REPO_FILE], None,
                      full_block(REPO_FILE, "x"), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "ANCHOR EDIT")

    def test_anchor_not_found_fails(self):
        s = step_text(1, "x", ["- MODIFY %s (ANCHOR EDIT)" % REPO_FILE], None,
                      search_block(REPO_FILE, "fun nothing()", "fun y()"), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "step 1:", "found 0")

    def test_anchor_duplicate_fails(self):
        s = step_text(1, "x", ["- MODIFY %s (ANCHOR EDIT)" % REPO_FILE], None,
                      search_block(REPO_FILE, "rate()", "r()"), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "found 2")

    def test_create_existing_file_fails(self):
        s = step_text(1, "x", ["- CREATE %s (FULL FILE)" % REPO_FILE], None,
                      full_block(REPO_FILE, "x"), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "already exists")

    def test_modify_missing_file_fails(self):
        s = step_text(1, "x", ["- MODIFY nope.kt (FULL FILE)"], None, full_block("nope.kt", "x"),
                      rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "does not exist")

    def test_read_range_out_of_bounds_fails(self):
        s = step1().replace("ValasApi.kt:1-5", "ValasApi.kt:1-99")
        _, res = self.run_plan({1: s})
        self.assertFail(res, "out of range")

    def test_read_missing_file_fails(self):
        s = step1().replace("ValasApi.kt:1-5", "Nope.kt:1-5")
        _, res = self.run_plan({1: s})
        self.assertFail(res, "does not exist")

    def test_over_budget_fails(self):
        s = step_text(1, "big", ["- CREATE big.kt (FULL FILE)"], None,
                      full_block("big.kt", "x" * 70000), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "over budget")

    def test_near_budget_warns(self):
        s = step_text(1, "big", ["- CREATE big.kt (FULL FILE)"], None,
                      full_block("big.kt", "x" * 26000), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertPass(res)
        self.assertIn("WARN step 1:", res[1])

    def test_budget_counts_written_code(self):
        # 40k chars: ~10k tokens to read the step + ~10k tokens for the model to write it back
        s = step_text(1, "big", ["- CREATE big.kt (FULL FILE)"], None,
                      full_block("big.kt", "x" * 40000), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertFail(res, "over budget")

    def test_too_many_steps_warns(self):
        steps = {}
        for i in range(1, 12):
            steps[i] = step_text(i, "s%d" % i, ["- CREATE f%d.kt (FULL FILE)" % i], None,
                                 full_block("f%d.kt" % i, "x"), rules=real_rules())
        _, res = self.run_plan(steps)
        self.assertPass(res)
        self.assertIn("more than 10 steps", res[1])

    def test_utf8_paths_content(self):
        s = step_text(1, "x", ["- CREATE app/Msg.kt (FULL FILE)"], None,
                      full_block("app/Msg.kt", 'val m = "Kurs valas — gagal"'), rules=real_rules())
        _, res = self.run_plan({1: s})
        self.assertPass(res)

    def test_usage_error(self):
        code, _ = run_script("check_plan.py")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
