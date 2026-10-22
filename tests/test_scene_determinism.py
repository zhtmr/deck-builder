"""브라우저로 scene 결정성 검사를 돌려 본다. playwright·chromium 이 없으면 건너뛴다."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "system-deck" / "scripts"
EX = ROOT / "skills" / "system-deck" / "examples" / "recap"

BAD = """const g = ctx.canvas2d();
const P = Array.from({length: 300}, () => ({x: Math.random() * ctx.width, y: Math.random() * ctx.height}));
ctx.loop((t, dt) => { g.clearRect(0, 0, ctx.width, ctx.height); g.fillStyle = '#fff';
  for (const p of P) { p.x += 40 * dt; g.fillRect(p.x % ctx.width, p.y, 3, 3); } });"""


def chromium_ok():
    if importlib.util.find_spec("playwright") is None:
        return False
    code = "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p: p.chromium.launch().close()"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60).returncode == 0


@unittest.skipUnless(chromium_ok(), "playwright·chromium 없음")
class SceneDeterminismTest(unittest.TestCase):
    def test_contract_scene_passes_and_random_scene_fails(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(EX / "scenes", tmp / "scenes")
            shutil.copy(EX / "system-model.json", tmp / "system-model.json")
            good = {"type": "scene", "title": "g", "steps": 1, "script_file": "scenes/voices-canvas.js", "notes": "n"}
            bad = {"type": "scene", "title": "b", "script": BAD, "notes": "n"}
            deck = {"model": "system-model.json", "slides": [good, {"type": "end", "asks": ["a"]}, bad]}
            (tmp / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, SCRIPTS / "build_deck.py", tmp / "deck.json", "-o", tmp / "deck.html"],
                           check=True, capture_output=True)
            r = subprocess.run([sys.executable, SCRIPTS / "render_check.py", tmp / "deck.html", "--determinism",
                                "--slides", "1,3"], capture_output=True, text=True, timeout=300)
            res = json.loads(r.stdout)
            bad_slides = {p.split(":")[0] for p in res["problems"] if "결정성" in p}
            self.assertEqual(bad_slides, {"slide 3"}, res["problems"])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
