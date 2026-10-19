#!/usr/bin/env python3
"""
publish_demo.py — 예시 장표를 다시 빌드해 GitHub Pages 용 docs/demo/ 로 복사한다.

GitHub Pages 는 master 브랜치의 /docs 를 서빙한다 (docs/index.html 이 랜딩 페이지).
사용: python tools/publish_demo.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "skills" / "system-deck" / "examples" / "recap"
BUILD = ROOT / "skills" / "system-deck" / "scripts" / "build_deck.py"
DEMO = ROOT / "docs" / "demo"
DECKS = ["deck-motion", "deck", "deck-toss", "deck-scene"]


def main():
    DEMO.mkdir(parents=True, exist_ok=True)
    for name in DECKS:
        out = EX / f"{name}.html"
        r = subprocess.run([sys.executable, str(BUILD), str(EX / f"{name}.json"), "-o", str(out)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            sys.exit(f"{name} 빌드 실패:\n{r.stderr}")
        shutil.copy2(out, DEMO / f"{name}.html")
        print(f"  docs/demo/{name}.html  {out.stat().st_size // 1024}KB")
    (ROOT / "docs" / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
