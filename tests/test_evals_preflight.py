import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "skills" / "system-deck" / "examples" / "recap"
sys.path.insert(0, str(ROOT / "skills" / "system-deck" / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))
import check_deck as cd  # noqa: E402
import preflight as pf  # noqa: E402


class PreflightPathsTest(unittest.TestCase):
    OK = {"python": True, "git": True, "playwright": True, "python-pptx": True,
          "markitdown": True, "pyhwp": False, "pyyaml": True, "cdn": True}

    def test_all_available(self):
        p = "\n".join(pf.paths(self.OK, offline=False))
        self.assertIn("비평: 가능", p)
        self.assertIn("PPTX: 가능", p)
        self.assertIn(".pdf", p)
        self.assertNotIn(".hwp ", p + " ")

    def test_no_playwright_skips_review(self):
        p = "\n".join(pf.paths({**self.OK, "playwright": False}, offline=False))
        self.assertIn("비평: 불가", p)
        self.assertIn("PPTX: 불가", p)
        self.assertIn("브라우저 인쇄", p)

    def test_no_cdn_and_offline(self):
        self.assertIn("CDN 불가", "\n".join(pf.paths({**self.OK, "cdn": False}, offline=False)))
        self.assertIn("네트워크 미확인", "\n".join(pf.paths({**self.OK, "cdn": None}, offline=True)))

    def test_offline_check_preserves_skipped_cdn(self):
        with mock.patch.object(pf, "chromium_ok", return_value=(False, "unavailable")), \
                mock.patch.object(pf, "has_module", return_value=False), \
                mock.patch.object(pf.shutil, "which", return_value="/usr/bin/git"), \
                mock.patch.object(pf, "reachable") as reachable:
            result = pf.check(offline=True)
        items = {item["key"]: item["ok"] for item in result["items"]}
        self.assertIsNone(items["cdn"])
        self.assertIs(items["git"], True)
        self.assertIs(items["playwright"], False)
        reachable.assert_not_called()
        stdout = io.StringIO()
        with mock.patch.object(pf, "check", return_value=result), \
                mock.patch.object(sys, "argv", ["preflight.py", "--offline"]), \
                contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exited:
            pf.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("· cdn", stdout.getvalue())


class CheckDeckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.d = self.tmp / ".deck"
        (self.d / "out").mkdir(parents=True)
        shutil.copy(EX / "deck-motion.json", self.d / "deck.json")
        shutil.copy(EX / "system-model.json", self.d / "system-model.json")
        shutil.copytree(EX / "assets", self.d / "assets")
        deck = json.loads((self.d / "deck.json").read_text(encoding="utf-8"))
        rows = "\n".join(f"| {i+1} | {s.get('title', '')} | {s['type']} | — |" for i, s in enumerate(deck["slides"]))
        (self.d / "outline.md").write_text(f"# t\n- 핵심 메시지: m\n\n{rows}\n", encoding="utf-8")
        (self.d / "out" / "deck.html").write_text("x", encoding="utf-8")
        (self.d / "out" / "sheet.png").write_bytes(b"x")
        (self.d / "critique_01.md").write_text(
            "# 비평 01\n\n## 독립 비평 (deck-critic)\n- (받은 판정을 옮겨 적는다)\n- 5번 다시 만듦: 숫자 없는 카드\n",
            encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def results(self, **kw):
        return {r["key"]: r for r in cd.check(self.d, **kw)}

    def test_complete_run_passes(self):
        r = self.results(slides="9-12", no_code=False)
        self.assertTrue(all(x["ok"] for x in r.values()), [x for x in r.values() if not x["ok"]])

    def test_failures_detected(self):
        (self.d / "critique_01.md").write_text("# 비평 01\n\n## 독립 비평 (deck-critic)\n- (받은 판정을 옮겨 적는다)\n",
                                               encoding="utf-8")
        (self.d / "outline.md").write_text("# t\n- 핵심 메시지: m\n| 1 | x |\n", encoding="utf-8")
        r = self.results(slides="5-6", no_code=True, doc_only=True)
        for k in ("independent_critique", "titles_from_outline", "slide_count", "no_code", "doc_only"):
            self.assertFalse(r[k]["ok"], k)

    def test_strict_warning_fails(self):
        deck = json.loads((self.d / "deck.json").read_text(encoding="utf-8"))
        deck["slides"][1].pop("notes", None)
        (self.d / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        r = self.results()
        self.assertFalse(r["strict_build"]["ok"])
        self.assertIn("노트", r["strict_build"]["detail"])

    def test_missing_deck_json(self):
        (self.d / "deck.json").unlink()
        self.assertEqual(self.results()["deck_json"]["ok"], False)

    def test_repo_untouched_only_ignores_deck_directory(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.tmp), *args], check=True, capture_output=True)

        git("init")
        (self.tmp / ".gitignore").write_text("# baseline\n", encoding="utf-8")
        fixture = self.tmp / "meeting-notes-plan.md"
        shutil.copy(ROOT / "evals" / "files" / fixture.name, fixture)
        git("add", ".gitignore", fixture.name)
        git("-c", "user.name=Eval Test", "-c", "user.email=eval@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "Fixture baseline")
        self.assertTrue(self.results(repo=self.tmp)["repo_untouched"]["ok"])
        for name in (".gitignore", fixture.name, ".deck.json", ".deck-backup", "other.txt"):
            with self.subTest(path=name):
                path = self.tmp / name
                baseline = path.read_bytes() if path.exists() else None
                path.write_text("changed\n", encoding="utf-8")
                result = self.results(repo=self.tmp)["repo_untouched"]
                self.assertFalse(result["ok"])
                self.assertIn(name, result["detail"])
                if baseline is None:
                    path.unlink()
                else:
                    path.write_bytes(baseline)


if __name__ == "__main__":
    unittest.main()
