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
        for name in ("deck.json", "deck-toss.json", "deck-motion.json", "deck-scene.json"):
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

    def test_topic_title(self):
        w = "\n".join(bd.lint(deck(
            {"type": "topology", "title": "전체 구성", "notes": "n"},
            {"type": "stats", "title": "결과", "items": [{"value": "1", "label": "b", "source": "s"}], "notes": "n"},
            {"type": "bullets", "title": "아키텍처", "bullets": ["x"], "notes": "n"})))
        self.assertEqual(w.count("주제형"), 3)

    def test_claim_title_and_exempt_types_pass(self):
        w = "\n".join(bd.lint(deck(
            {"type": "topology", "title": "무거운 처리는 요청 경로 밖으로 뺐다", "notes": "n"},
            {"type": "section", "title": "아키텍처"},
            {"type": "statement", "text": "x", "notes": "n"})))
        self.assertNotIn("주제형", w)

    def test_end_without_asks_warns(self):
        self.assertIn("asks", "\n".join(bd.lint(deck({"type": "end", "title": "감사합니다"}))))
        self.assertNotIn("asks", "\n".join(bd.lint(deck({"type": "end", "title": "승인해 주세요", "asks": ["예산 승인"]}))))

    def test_end_asks_validation(self):
        self.assertTrue(any("asks" in e for e in errs({"type": "end", "asks": []})))
        self.assertTrue(any("asks" in e for e in errs({"type": "end", "asks": ["a", "b", "c", "d"]})))
        self.assertTrue(any("asks" in e for e in errs({"type": "end", "asks": [1]})))
        self.assertEqual(errs({"type": "end", "asks": ["a"]}), [])


class RhythmTest(unittest.TestCase):
    def rhythm(self, *slides, steps=None, **top):
        d = {**deck(*slides), **top}
        return "\n".join(bd.rhythm(d, steps or [0] * len(slides)))

    def test_same_type_run(self):
        st = {"type": "stats", "items": []}
        self.assertIn("'stats' 가 3장 연속", self.rhythm(st, st, st))
        self.assertEqual(self.rhythm(st, st, {"type": "bento"}, st), "")

    def test_adjacent_bullets(self):
        b = {"type": "bullets", "bullets": ["x"]}
        w = self.rhythm(b, b, b)
        self.assertEqual(w.count("텍스트 장"), 2)
        self.assertNotIn("연속", w)
        self.assertEqual(self.rhythm(b, {"type": "topology"}, b), "")

    def test_statement_count(self):
        s, e = {"type": "statement", "text": "x"}, {"type": "end"}
        self.assertEqual(self.rhythm(s, e, s), "")
        self.assertIn("statement 가 3장", self.rhythm(s, e, s, e, s))

    def test_steps_cap_per_type(self):
        self.assertIn("스텝 8개 > 7", self.rhythm({"type": "bento"}, steps=[8]))
        self.assertEqual(self.rhythm({"type": "flow"}, steps=[12]), "")
        self.assertIn("스텝 13개 > 12", self.rhythm({"type": "flow"}, steps=[13]))

    def test_transition_kinds(self):
        sl = [{"type": t, "transition": tr} for t, tr in (("section", "zoom"), ("bento", "fade"), ("end", "slide-up"))]
        self.assertIn("전환 4종", self.rhythm({"type": "title"}, *sl))
        self.assertEqual(self.rhythm(*sl), "")
        self.assertEqual(self.rhythm({"type": "title"}, *sl[:2], transition="fade"), "")

    def test_build_reports_rhythm(self):
        st = {"type": "stats", "items": [{"value": "1", "label": "a", "source": "s"}], "notes": "n",
              "title": "처리 시간이 줄었다"}
        p = ROOT / "tests" / "_rhythm.json"
        p.write_text(json.dumps({"model": MODEL, "slides": [st, st, st]}, ensure_ascii=False), encoding="utf-8")
        try:
            self.assertEqual(bd.build(p, None, True), 0)
            self.assertEqual(bd.build(p, None, True, strict=True), 1)
        finally:
            p.unlink(missing_ok=True)


class RenderTest(unittest.TestCase):
    def render(self, s):
        return bd.slide_html(0, s, MODEL, deck(s))

    def test_end_asks_render(self):
        h, steps = self.render({"type": "end", "title": "승인해 주세요", "asks": ["예산 승인", "인력 1명"]})
        self.assertEqual(steps, 2)
        self.assertIn('class="asks"', h)
        self.assertIn("요청 사항", h)
        h, steps = self.render({"type": "end"})
        self.assertEqual(steps, 0)
        self.assertIn("감사합니다", h)

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

    def test_scene_validation(self):
        ok = {"type": "scene", "script": "return {}", "libs": ["gsap", {"name": "d3", "url": "https://x/d3.js"}], "steps": 3}
        self.assertEqual(errs(ok), [])
        self.assertTrue(errs({"type": "scene"}))                                                # 스크립트 없음
        self.assertTrue(errs({"type": "scene", "script": "a", "script_file": "a.js"}))          # 둘 다
        self.assertTrue(errs({"type": "scene", "script": "a", "libs": ["jquery"]}))             # 내장 아님
        self.assertTrue(errs({"type": "scene", "script": "a", "libs": [{"name": "x-y", "url": "u"}]}))   # 식별자 아님
        self.assertTrue(errs({"type": "scene", "script": "a", "libs": [{"name": "x", "url": "u", "src": "s"}]}))
        self.assertTrue(errs({"type": "scene", "script": "a", "steps": 99}))
        self.assertTrue(errs({"type": "scene", "script": "a", "steps": True}))

    def test_scene_render(self):
        s = {"type": "scene", "title": "t", "script": "return {}", "steps": 2, "full": True,
             "html": "<div class=x></div>", "css": ":scope .x{color:red}"}
        html, steps = self.render(s)
        self.assertEqual(steps, 2)
        self.assertIn('data-scene="0"', html)
        self.assertIn("t-scene full", html)
        self.assertIn("<div class=x></div>", html)        # 작성자 마크업은 그대로
        self.assertIn("#s0-scene .x{color:red}", html)    # :scope 는 장면 영역으로

    def test_scene_js_wraps_and_escapes(self):
        js = bd.scene_js(3, {"type": "scene", "script": "el.innerHTML = '</script>'", "libs": ["three"]})
        self.assertTrue(js.startswith("__SCENES[3] = "))
        self.assertNotIn("</script", js)
        self.assertIn('"module": true', js)
        self.assertIn("three@", js)

    def test_scene_lint_fallback(self):
        w = "\n".join(bd.lint(deck({"type": "scene", "script": "a", "libs": ["gsap"], "notes": "n"})))
        self.assertIn("fallback", w)
        w = "\n".join(bd.lint(deck({"type": "scene", "script": "a", "notes": "n"})))
        self.assertNotIn("fallback", w)

    def test_scene_lint_determinism(self):
        def w(code):
            return "\n".join(bd.lint(deck({"type": "scene", "script": code, "notes": "n"})))
        self.assertIn("ctx.rand", w("const x = Math.random() * W;"))
        self.assertIn("시계", w("const t0 = performance.now();"))
        self.assertIn("타이머", w("setTimeout(draw, 16);"))
        self.assertIn("dt 누적", w("ctx.loop((t, dt) => { p.x += v * dt; });"))
        clean = ("const x = ctx.rand(i, 1) * W; // Math.random 대신\n"
                 "ctx.loop((t, dt, { ts }) => { const x = x0 + v * t; });")
        self.assertNotIn("결정성", w(clean))

    def test_examples_follow_determinism(self):
        for s in json.loads((EX / "deck-scene.json").read_text(encoding="utf-8"))["slides"]:
            if s["type"] == "scene":
                code = (EX / s["script_file"]).read_text(encoding="utf-8")
                self.assertNotIn("결정성", "\n".join(bd.lint(deck({**s, "script": code}))), s["script_file"])

    def test_template_exposes_seek(self):
        tpl = (SCRIPTS / "deck_template.html").read_text(encoding="utf-8")
        self.assertIn("seek, count", tpl)
        self.assertIn("rand: (i, salt = 0)", tpl)

    def test_html_escaped(self):
        html, _ = self.render({"type": "bento", "cards": [{"title": "<script>x</script>"}, {"title": "b"}]})
        self.assertNotIn("<script>x", html)


if __name__ == "__main__":
    unittest.main()
