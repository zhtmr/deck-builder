import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "system-deck" / "scripts"
EX = ROOT / "skills" / "system-deck" / "examples" / "recap"
sys.path.insert(0, str(SCRIPTS))
import build_deck as bd  # noqa: E402

MODEL = json.loads((EX / "system-model.json").read_text(encoding="utf-8"))
MODEL.setdefault("flows", [])


def deck(*slides):
    return {"title": "t", "slides": list(slides)}


def errs(*slides):
    return bd.validate(MODEL, deck(*slides))


class ExamplesTest(unittest.TestCase):
    def test_example_decks_validate_and_build(self):
        for name in ("deck.json", "deck-toss.json", "deck-motion.json"):
            with self.subTest(name):
                d = json.loads((EX / name).read_text(encoding="utf-8"))
                self.assertEqual(bd.validate(MODEL, d), [])
                out = ROOT / "tests" / f"_out_{name}.html"
                try:
                    self.assertEqual(bd.build(EX / name, out, False), 0)
                    self.assertIn("<section", out.read_text(encoding="utf-8"))
                finally:
                    out.unlink(missing_ok=True)


class SchemaTest(unittest.TestCase):
    def test_missing_required(self):
        self.assertTrue(any("필수 필드 'items'" in e for e in errs({"type": "terminal"})))
        self.assertTrue(any("필수 필드 'cards'" in e for e in errs({"type": "bento"})))

    def test_counts(self):
        self.assertTrue(any("2~4개" in e for e in errs({"type": "bento", "cards": [{"title": "a"}]})))
        self.assertTrue(any("2~6개" in e for e in errs({"type": "timeline", "items": [{"period": "a", "title": "b"}]})))

    def test_terminal_status_and_progress(self):
        e = errs({"type": "terminal", "items": [{"label": "x", "status": "DONE", "progress": 150}]})
        self.assertTrue(any("status" in x for x in e))
        self.assertTrue(any("progress" in x for x in e))

    def test_walk_range(self):
        code = "a\nb\nc"
        self.assertEqual(errs({"type": "code", "code": code, "walk": [{"lines": [1, 3], "note": "n"}]}), [])
        self.assertTrue(errs({"type": "code", "code": code, "walk": [{"lines": [2, 9], "note": "n"}]}))
        self.assertTrue(errs({"type": "code", "code": code, "walk": [{"lines": "x"}]}))
        self.assertEqual(errs({"type": "code", "code": code, "start_line": 10,
                               "walk": [{"lines": 11, "note": "n"}]}), [])

    def test_unknown_type(self):
        self.assertTrue(any("알 수 없는 type" in e for e in errs({"type": "hero"})))


class LintTest(unittest.TestCase):
    def test_length_and_unknown_field(self):
        w = bd.lint(deck({"type": "bullets", "title": "가" * 30, "bullets": ["나" * 50], "bulets": 1, "notes": "n"}))
        joined = "\n".join(w)
        self.assertIn("제목 30자 > 28자", joined)
        self.assertIn("불릿 50자 > 45자", joined)
        self.assertIn("알 수 없는 필드 'bulets'", joined)

    def test_markup_not_counted(self):
        w = bd.lint(deck({"type": "bullets", "title": "**" + "가" * 28 + "**", "bullets": ["x"], "notes": "n"}))
        self.assertFalse(any("제목" in x for x in w))

    def test_source_missing_for_terminal_and_stats(self):
        w = "\n".join(bd.lint(deck(
            {"type": "terminal", "items": [{"label": "a"}], "notes": "n"},
            {"type": "stats", "items": [{"value": "1", "label": "b"}], "notes": "n"})))
        self.assertIn("항목 'a' 에 source 없음", w)
        self.assertIn("지표 'b' 에 source 없음", w)

    def test_placeholder_and_notes(self):
        w = "\n".join(bd.lint(deck({"type": "bullets", "bullets": ["[확인 필요: 사용자 수]"]})))
        self.assertIn("[확인 필요]", w)
        self.assertIn("노트", w)


class RenderTest(unittest.TestCase):
    def render(self, s):
        return bd.slide_html(0, s, MODEL, deck(s))

    def test_count_html(self):
        self.assertIn('data-to="1600000.0"', bd.count_html("1,600,000 req/s"))
        self.assertIn('data-comma="1"', bd.count_html("1,600,000"))
        self.assertIn('data-dec="1"', bd.count_html("1.8ms"))
        self.assertTrue(bd.count_html("+340%").startswith("+"))
        # 숫자가 여럿(날짜/범위)이거나 끄면 카운트하지 않는다
        self.assertNotIn("num", bd.count_html("2026.10 ~ 2027.03"))
        self.assertNotIn("num", bd.count_html("1시간 → 5분"))
        self.assertNotIn("num", bd.count_html("42ms", enabled=False))
        self.assertNotIn("num", bd.count_html("없음"))

    def test_terminal_steps_and_status(self):
        html, steps = self.render({"type": "terminal", "title": "t", "command": "ls",
                                   "items": [{"label": "a", "status": "ok"}, {"label": "b", "status": "FAIL"}],
                                   "summary": "끝"})
        self.assertEqual(steps, 3)
        self.assertIn("[OK]", html)
        self.assertIn("tsum frag fail", html)   # 가장 나쁜 상태를 따른다
        self.assertIn('data-full="ls"', html)

    def test_code_walk_steps(self):
        html, steps = self.render({"type": "code", "code": "a\nb\nc",
                                   "walk": [{"lines": 1, "note": "x"}, {"lines": [2, 3], "note": "y"}]})
        self.assertEqual(steps, 2)
        self.assertIn("data-walk=", html)
        self.assertEqual(html.count('class="walk"'), 2)

    def test_bento_timeline_steps(self):
        _, n = self.render({"type": "bento", "cards": [{"title": "a"}, {"title": "b"}, {"title": "c"}]})
        self.assertEqual(n, 3)
        _, n = self.render({"type": "timeline", "items": [{"period": "1", "title": "a"}, {"period": "2", "title": "b"}]})
        self.assertEqual(n, 2)

    def test_words_wraps_text_but_not_tags(self):
        h = bd.words("가나 <b>다라 마</b> **")
        self.assertIn('<b><span class="w" style="--i:1">다라</span>', h)
        self.assertEqual(h.count('class="w"'), 4)

    def test_statement_quote_and_transition_attr(self):
        html, _ = self.render({"type": "statement", "text": "한 줄 **강조**", "transition": "zoom"})
        self.assertIn('data-tr="zoom"', html)
        self.assertIn("statement words", html)
        html, _ = self.render({"type": "quote", "quote": "인용", "by": "누구"})
        self.assertIn("<blockquote", html)
        self.assertIn('data-tr="slide-left"', html)   # 기본 전환

    def test_magic_move(self):
        s = {"type": "code", "magic": [{"code": "a\nb", "note": "1"}, {"code": "a\nc\nd", "note": "2"}]}
        self.assertEqual(errs(s), [])
        html, steps = self.render(s)
        self.assertEqual(steps, 1)
        self.assertIn("data-magic=", html)
        self.assertIn(" big", html)   # 짧은 코드는 큰 글씨

    def test_magic_validation(self):
        self.assertTrue(errs({"type": "code", "magic": [{"code": "a"}]}))                       # 버전 1개
        self.assertTrue(errs({"type": "code", "code": "a", "magic": [{"code": "a"}, {"code": "b"}]}))  # code 와 동시 사용
        self.assertTrue(errs({"type": "code"}))                                                  # 둘 다 없음

    def test_transition_and_fx_validation(self):
        self.assertTrue(errs({"type": "end", "transition": "spin"}))
        self.assertTrue(errs({"type": "end", "fx": "bounce"}))
        self.assertEqual(errs({"type": "end", "transition": "fade", "fx": "scale"}), [])
        self.assertTrue(bd.validate(MODEL, {"transition": "spin", "slides": []}))

    def test_long_stat_value_class(self):
        html, _ = self.render({"type": "stats", "items": [{"value": "1,600,000", "label": "a"}]})
        self.assertIn('class="v long"', html)

    def test_html_escaped(self):
        html, _ = self.render({"type": "bento", "cards": [{"title": "<script>x</script>"}, {"title": "b"}]})
        self.assertNotIn("<script>x", html)


if __name__ == "__main__":
    unittest.main()
