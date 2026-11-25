from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts scripts/ on sys.path)
from helpers import SECTION_ORDER, full_block, search_block, step_text

import mandor_plan as mp


def write_step(n, text, name=None) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / (name or "step-%d.md" % n)
    p.write_text(text, encoding="utf-8")
    return p


VALID_CHANGES = ["- MODIFY app/A.kt (ANCHOR EDIT)", "- CREATE app/ATest.kt (FULL FILE)"]
VALID_BLOCKS = search_block("app/A.kt", "val x = 1", "val x = 2") + "\n" + \
    full_block("app/ATest.kt", "class ATest {\n}\n")


class ParseStepTest(unittest.TestCase):
    def test_parse_valid_step(self):
        p = write_step(2, step_text(2, "Fix A", VALID_CHANGES, ["- app/B.kt:1-40"], VALID_BLOCKS))
        s = mp.parse_step(p)
        self.assertEqual(s.errors, [])
        self.assertEqual(s.number, 2)
        self.assertEqual(s.title, "Fix A")
        self.assertEqual(s.changes, [mp.FileChange("MODIFY", "app/A.kt", "ANCHOR EDIT"),
                                     mp.FileChange("CREATE", "app/ATest.kt", "FULL FILE")])
        self.assertEqual(s.reads, [mp.ReadRef("app/B.kt", 1, 40)])
        self.assertEqual(s.blocks, [mp.Block("app/A.kt", "SEARCH", "val x = 1", "val x = 2"),
                                    mp.Block("app/ATest.kt", "FULL", None, "class ATest {\n}\n")])

    def test_reads_none(self):
        s = mp.parse_step(write_step(1, step_text(1, changes=VALID_CHANGES, blocks=VALID_BLOCKS)))
        self.assertEqual(s.reads, [])
        self.assertEqual(s.errors, [])

    def test_delete_change(self):
        s = mp.parse_step(write_step(1, step_text(1, changes=["- DELETE app/Old.kt"])))
        self.assertEqual(s.changes, [mp.FileChange("DELETE", "app/Old.kt", None)])
        self.assertEqual(s.errors, [])

    def test_missing_section_reported(self):
        order = [x for x in SECTION_ORDER if x != "FORBIDDEN"]
        s = mp.parse_step(write_step(1, step_text(1, changes=VALID_CHANGES, blocks=VALID_BLOCKS,
                                                  order=order)))
        self.assertIn("missing section FORBIDDEN", s.errors)

    def test_section_order_enforced(self):
        order = ["EXECUTOR RULES", "FILES TO CHANGE", "FILES TO READ", "CHANGES", "GOAL",
                 "FORBIDDEN", "DONE WHEN"]
        s = mp.parse_step(write_step(1, step_text(1, changes=VALID_CHANGES, blocks=VALID_BLOCKS,
                                                  order=order)))
        self.assertTrue(any("section order" in e for e in s.errors), s.errors)

    def test_create_requires_full_file(self):
        s = mp.parse_step(write_step(1, step_text(1, changes=["- CREATE x.kt (ANCHOR EDIT)"])))
        self.assertTrue(any("CREATE" in e and "FULL FILE" in e for e in s.errors), s.errors)

    def test_bad_change_line(self):
        s = mp.parse_step(write_step(1, step_text(1, changes=["- EDIT x.kt"])))
        self.assertTrue(any("invalid FILES TO CHANGE line" in e for e in s.errors), s.errors)

    def test_bad_read_line(self):
        s = mp.parse_step(write_step(1, step_text(1, changes=VALID_CHANGES, blocks=VALID_BLOCKS,
                                                  reads=["- app/B.kt:40-1"])))
        self.assertTrue(any("invalid FILES TO READ line" in e for e in s.errors), s.errors)

    def test_marker_mismatch(self):
        s = mp.parse_step(write_step(2, step_text(2, changes=VALID_CHANGES, blocks=VALID_BLOCKS,
                                                  marker=3)))
        self.assertTrue(any("marker" in e for e in s.errors), s.errors)

    def test_unterminated_block(self):
        blocks = "FILE: app/A.kt\n<<<<<<< SEARCH\nval x = 1\n=======\nval x = 2\n"
        s = mp.parse_step(write_step(1, step_text(1, changes=VALID_CHANGES[:1], blocks=blocks)))
        self.assertTrue(any("unterminated" in e for e in s.errors), s.errors)

    def test_header_like_line_inside_block_is_content(self):
        blocks = full_block("docs/N.md", "## not a section\ntext\n")
        s = mp.parse_step(write_step(1, step_text(1, changes=["- CREATE docs/N.md (FULL FILE)"],
                                                  blocks=blocks)))
        self.assertEqual(s.errors, [])
        self.assertEqual(s.blocks[0].text, "## not a section\ntext\n")


class ApplyBlocksTest(unittest.TestCase):
    def test_apply_search_unique(self):
        out, errs = mp.apply_blocks("a\nval x = 1\nb\n", [mp.Block("f", "SEARCH", "val x = 1", "val x = 2")])
        self.assertEqual((out, errs), ("a\nval x = 2\nb\n", []))

    def test_apply_search_missing(self):
        out, errs = mp.apply_blocks("a\n", [mp.Block("f", "SEARCH", "zzz", "y")])
        self.assertEqual(out, "a\n")
        self.assertEqual(errs, ["SEARCH block not unique in f (found 0)"])

    def test_apply_search_duplicate(self):
        out, errs = mp.apply_blocks("x\nx\n", [mp.Block("f", "SEARCH", "x", "y")])
        self.assertEqual(errs, ["SEARCH block not unique in f (found 2)"])

    def test_apply_search_on_missing_file(self):
        out, errs = mp.apply_blocks(None, [mp.Block("f", "SEARCH", "x", "y")])
        self.assertIsNone(out)
        self.assertEqual(errs, ["SEARCH block on missing file f"])

    def test_apply_full_file(self):
        out, errs = mp.apply_blocks(None, [mp.Block("f", "FULL", None, "new\n")])
        self.assertEqual((out, errs), ("new\n", []))

    def test_utf8_content(self):
        text = 'val msg = "Kurs valas tidak tersedia — coba lagi"'
        p = write_step(1, step_text(1, changes=["- MODIFY app/A.kt (ANCHOR EDIT)"],
                                    blocks=search_block("app/A.kt", "val msg = \"\"", text)))
        s = mp.parse_step(p)
        self.assertEqual(s.errors, [])
        out, _ = mp.apply_blocks('val msg = ""\n', s.blocks)
        self.assertEqual(out, text + "\n")


class MiscTest(unittest.TestCase):
    def test_estimate_tokens(self):
        self.assertEqual(mp.estimate_tokens("a" * 401), 101)
        self.assertEqual(mp.estimate_tokens(""), 0)

    def test_read_meta(self):
        d = Path(tempfile.mkdtemp())
        (d / "meta").write_text("repo=/x y\nbase=abc\n\n# c\ntask=a=b\n", encoding="utf-8")
        self.assertEqual(mp.read_meta(d), {"repo": "/x y", "base": "abc", "task": "a=b"})

    def test_read_meta_missing(self):
        self.assertEqual(mp.read_meta(Path(tempfile.mkdtemp())), {})

    def test_constants(self):
        self.assertEqual(mp.SECTIONS, SECTION_ORDER)
        self.assertEqual((mp.BUDGET, mp.WARN_AT, mp.MAX_FILES_PER_STEP, mp.MAX_STEPS),
                         (16000, 12000, 2, 10))


if __name__ == "__main__":
    unittest.main()
