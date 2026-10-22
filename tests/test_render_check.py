import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "system-deck" / "scripts"))
import render_check as rc  # noqa: E402


class SheetHelpersTest(unittest.TestCase):
    def test_pick_steps_keeps_all_when_few(self):
        self.assertEqual(rc.pick_steps(3), [0, 1, 2, 3])
        self.assertEqual(rc.pick_steps(5), [0, 1, 2, 3, 4, 5])

    def test_pick_steps_samples_first_and_last(self):
        got = rc.pick_steps(12)
        self.assertEqual(len(got), rc.STEP_COLS)
        self.assertEqual((got[0], got[-1]), (0, 12))
        self.assertEqual(got, sorted(set(got)))

    def test_paths_split_only_when_needed(self):
        out = Path("out/sheet.png")
        self.assertEqual(rc.paths(out, 1), [out])
        self.assertEqual(rc.paths(out, 2), [Path("out/sheet_01.png"), Path("out/sheet_02.png")])

    def test_chunks(self):
        self.assertEqual(rc.chunks([1, 2, 3], 2), [[1, 2], [3]])
        self.assertEqual(rc.chunks([], 2), [[]])

    def test_sheet_html_escapes_labels(self):
        h = rc.sheet_html([{"label": "<b>", "cells": [(b"x", "a&b")]}], 3, 480)
        self.assertIn("&lt;b&gt;", h)
        self.assertIn("a&amp;b", h)
        self.assertIn("repeat(3,480px)", h)


if __name__ == "__main__":
    unittest.main()
