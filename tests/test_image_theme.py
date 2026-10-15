import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "system-deck" / "scripts"))
import build_deck as bd  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001"
                    "e221bc330000000049454e44ae426082")


def write_deck(tmp: Path, slides, **extra):
    (tmp / "shot.png").write_bytes(PNG)
    d = {"title": "t", "model": {"nodes": [], "edges": []}, "slides": slides, **extra}
    p = tmp / "deck.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


class ImageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def build(self, slides, **extra):
        p = write_deck(self.tmp, slides, **extra)
        out = self.tmp / "o.html"
        rc = bd.build(p, out, False)
        return rc, (out.read_text(encoding="utf-8") if out.exists() else "")

    def test_local_image_inlined_as_data_uri(self):
        rc, html = self.build([{"type": "image", "src": "shot.png", "alt": "a", "notes": "n"}])
        self.assertEqual(rc, 0)
        self.assertIn("data:image/png;base64,", html)

    def test_remote_src_passthrough(self):
        self.assertEqual(bd.image_src("https://x.dev/a.png"), "https://x.dev/a.png")

    def test_missing_file_is_error(self):
        rc, _ = self.build([{"type": "image", "src": "nope.png"}])
        self.assertEqual(rc, 1)

    def test_marks_become_steps_and_flip_label_near_bottom(self):
        bd.BASE_DIR = self.tmp
        (self.tmp / "shot.png").write_bytes(PNG)
        html, steps = bd.slide_html(0, {"type": "image", "src": "shot.png",
                                        "marks": [{"box": [10, 10, 20, 20], "note": "위"}, {"box": [10, 70, 20, 20], "note": "아래"}]},
                                    {"nodes": [], "edges": [], "flows": []}, {})
        self.assertEqual(steps, 2)
        self.assertEqual(html.count('class="mark frag'), 2)
        self.assertEqual(html.count("mark frag up"), 1)

    def test_marks_validation(self):
        def e(marks):
            return bd.validate_slide(0, {"type": "image", "src": "x", "marks": marks})
        self.assertEqual(e([{"box": [0, 0, 50, 50]}]), [])
        self.assertTrue(e([{"box": [60, 0, 50, 50]}]))      # x+w > 100
        self.assertTrue(e([{"box": [0, 0, 50]}]))            # 원소 3개
        self.assertTrue(e([{"note": "박스 없음"}]))
        self.assertTrue(bd.validate_slide(0, {"type": "image", "src": "x", "fit": "stretch"}))

    def test_lint_alt_missing(self):
        w = "\n".join(bd.lint({"slides": [{"type": "image", "src": "x", "notes": "n"}]}))
        self.assertIn("alt", w)


class ThemeTest(unittest.TestCase):
    def test_default_theme_is_aurora_with_accent(self):
        tmp = Path(tempfile.mkdtemp())
        p = write_deck(tmp, [{"type": "end"}])
        out = tmp / "o.html"
        self.assertEqual(bd.build(p, out, False), 0)
        html = out.read_text(encoding="utf-8")
        self.assertIn('data-theme="aurora"', html)
        self.assertIn(bd.ACCENTS["aurora"], html)

    def test_unknown_theme_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        p = write_deck(tmp, [{"type": "end"}], theme="neon")
        with self.assertRaises(bd.DeckError):
            bd.build(p, tmp / "o.html", False)

    def test_all_themes_build(self):
        for th in bd.THEMES:
            with self.subTest(th):
                tmp = Path(tempfile.mkdtemp())
                p = write_deck(tmp, [{"type": "end"}], theme=th)
                self.assertEqual(bd.build(p, tmp / "o.html", False), 0)


if __name__ == "__main__":
    unittest.main()
