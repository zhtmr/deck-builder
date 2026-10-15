#!/usr/bin/env python3
"""
record_media.py — 예시 장표를 실제로 구동해 README 용 GIF 와 스크린샷을 만든다.

예시 HTML(`skills/system-deck/examples/recap/*.html`)을 헤드리스 브라우저로 열어 → 키를 실제로 눌러
애니메이션이 진행되는 동안 프레임을 캡처하고, Pillow 로 GIF 를 조립한다. 결과는 docs/media/ 에 저장된다.

필요: pip install playwright pillow && python -m playwright install chromium
사용: python tools/record_media.py [--only gifs|shots] [--width 800]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

try:
    from PIL import Image
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("pip install playwright pillow && python -m playwright install chromium")

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "skills" / "system-deck" / "examples" / "recap"
OUT = ROOT / "docs" / "media"
STAGE_W, STAGE_H = 1600, 900


class Recorder:
    """CDP 스크린캐스트로 브라우저가 보내는 프레임을 실시간 타임스탬프와 함께 받아 GIF 로 만든다.
    (스크린샷 반복 방식은 프레임당 ~250ms 가 걸려 4fps 로 끊겨서 쓰지 않는다)

    화면이 바뀔 때만 프레임이 오므로 정지 구간은 프레임 하나가 길게 유지된다."""

    def __init__(self, page, width: int, fps: int):
        self.page, self.width, self.fps = page, width, fps
        self.raw: list[tuple[bytes, float]] = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.cdp.send("Page.startScreencast", {
            "format": "png", "maxWidth": width, "maxHeight": round(width * STAGE_H / STAGE_W), "everyNthFrame": 1})
        self.page.wait_for_timeout(250)

    def _on_frame(self, ev):
        import base64
        self.raw.append((base64.b64decode(ev["data"]), ev["metadata"]["timestamp"]))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:   # 종료 직전에 늦게 도착한 프레임: 무시
            pass

    def capture(self, seconds: float):
        self.page.wait_for_timeout(int(seconds * 1000))

    def save(self, path: Path, colors: int | None = None, tail_s: float = 1.4):
        colors = colors or COLORS
        self.cdp.send("Page.stopScreencast")
        self.cdp.remove_listener("Page.screencastFrame", self._on_frame)
        if not self.raw:
            sys.exit("프레임을 받지 못했습니다")
        t0, t_end = self.raw[0][1], self.raw[-1][1] + tail_s
        step = 1.0 / self.fps
        picks: list[tuple[int, float]] = []          # (원본 프레임 인덱스, 지속 시간)
        j, tick = 0, t0
        while tick < t_end:
            while j + 1 < len(self.raw) and self.raw[j + 1][1] <= tick:
                j += 1
            if picks and picks[-1][0] == j:
                picks[-1] = (j, picks[-1][1] + step)  # 같은 화면이 이어지면 지속 시간만 늘린다
            else:
                picks.append((j, step))
            tick += step
        ims, durs = [], []
        for idx, d in picks:
            im = Image.open(io.BytesIO(self.raw[idx][0])).convert("RGB")
            ims.append(im.convert("P", palette=Image.ADAPTIVE, colors=colors, dither=Image.Dither.NONE))
            durs.append(max(20, int(d * 1000)))
        path.parent.mkdir(parents=True, exist_ok=True)
        ims[0].save(path, save_all=True, append_images=ims[1:], duration=durs, loop=0, optimize=True, disposal=1)
        print(f"  {path.relative_to(ROOT)}  {len(ims)}프레임  {sum(durs) / 1000:.1f}s  {path.stat().st_size / 1024 / 1024:.1f}MB")


def slide_index(page, type_: str, nth: int = 0) -> int:
    return page.evaluate(
        """([t, n]) => [...document.querySelectorAll('.slide')].map((s,i)=>[s.className.includes('t-'+t), i])
           .filter(x=>x[0]).map(x=>x[1])[n]""", [type_, nth])


def scene(rec: Recorder, page, idx: int, entry: float, steps: int, hold: float, last_hold: float | None = None):
    """idx 번째 슬라이드로 이동(전환 연출 포함)해 entry 초 녹화한 뒤, → 키를 steps 번 누르며 hold 초씩 녹화."""
    page.evaluate(f"deck.go({idx}, 0)")
    rec.capture(entry)
    for k in range(steps):
        page.keyboard.press("ArrowRight")
        rec.capture(last_hold if (last_hold and k == steps - 1) else hold)


def open_deck(p, name: str, dsf: float = 1.0, still: bool = False):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": STAGE_W, "height": STAGE_H}, device_scale_factor=dsf)
    pg.goto((EX / name).as_uri() + ("?still=1" if still else ""))
    pg.wait_for_timeout(900)
    return b, pg


COLORS = 64


def make_gifs(width: int, fps: int):
    with sync_playwright() as p:
        # 1) 시스템 토폴로지: 자동 순환 → 한 단계씩 진행하는 요청 흐름
        b, pg = open_deck(p, "deck.html")
        rec = Recorder(pg, width, fps)
        topo = slide_index(pg, "topology", 0)
        flow = slide_index(pg, "flow", 0)
        pg.evaluate("deck.go(0, 0)"); rec.capture(2.2)
        scene(rec, pg, topo, entry=5.2, steps=0, hold=0)
        n = min(6, pg.evaluate(f"deck.steps({flow})"))
        scene(rec, pg, flow, entry=1.6, steps=n, hold=1.5)
        rec.save(OUT / "topology-flow.gif")
        b.close()

        # 2) 모션 슬라이드 ①: 터미널 → 숫자 카운트업 → 벤토
        b, pg = open_deck(p, "deck-motion.html")
        rec = Recorder(pg, width, fps)
        pg.evaluate("deck.go(0, 0)"); rec.capture(2.4)
        scene(rec, pg, slide_index(pg, "terminal"), entry=2.2, steps=4, hold=1.5)
        scene(rec, pg, slide_index(pg, "stats"), entry=1.0, steps=3, hold=1.9)
        scene(rec, pg, slide_index(pg, "bento"), entry=0.8, steps=4, hold=1.0, last_hold=1.8)
        rec.save(OUT / "motion-terminal-stats-bento.gif")

        # 3) 모션 슬라이드 ②: 스크린샷 하이라이트 → 코드 매직무브 → 핵심 문장
        rec = Recorder(pg, width, fps)
        scene(rec, pg, slide_index(pg, "image"), entry=1.6, steps=3, hold=1.5)
        magic = pg.evaluate("[...document.querySelectorAll('.slide')].findIndex(s=>s.dataset.magic)")
        scene(rec, pg, magic, entry=1.8, steps=2, hold=2.2)
        scene(rec, pg, slide_index(pg, "statement"), entry=2.6, steps=0, hold=0)
        rec.save(OUT / "motion-image-magicmove.gif")
        b.close()


def make_shots(width: int):
    """각 슬라이드 타입의 '모든 스텝이 끝난' 모습을 PNG 로."""
    jobs = [  # (html, 파일명, 선택자: (type, nth) 또는 'magic')
        ("deck-motion.html", "title", ("title", 0)),
        ("deck-motion.html", "image", ("image", 0)),
        ("deck-motion.html", "terminal", ("terminal", 0)),
        ("deck-motion.html", "stats", ("stats", 0)),
        ("deck-motion.html", "bento", ("bento", 0)),
        ("deck-motion.html", "code-magic-move", "magic"),
        ("deck-motion.html", "statement", ("statement", 0)),
        ("deck-motion.html", "timeline", ("timeline", 0)),
        ("deck.html", "topology", ("topology", 0)),
        ("deck.html", "flow", ("flow", 0)),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        cache: dict[str, tuple] = {}
        for html, name, sel in jobs:
            if html not in cache:
                cache[html] = open_deck(p, html, dsf=width / STAGE_W, still=True)
            _, pg = cache[html]
            i = (pg.evaluate("[...document.querySelectorAll('.slide')].findIndex(s=>s.dataset.magic)")
                 if sel == "magic" else slide_index(pg, *sel))
            pg.evaluate(f"deck.go({i}, deck.steps({i}), true)")
            pg.wait_for_timeout(350)
            f = OUT / f"{name}.png"
            pg.screenshot(path=str(f))
            print(f"  {f.relative_to(ROOT)}  {f.stat().st_size // 1024}KB")
        # 오버뷰 (o 키)
        _, pg = cache["deck-motion.html"]
        pg.evaluate("deck.go(2, 0, true)")
        pg.keyboard.press("o")
        pg.wait_for_timeout(500)
        f = OUT / "overview.png"
        pg.screenshot(path=str(f))
        print(f"  {f.relative_to(ROOT)}  {f.stat().st_size // 1024}KB")
        for b, _ in cache.values():
            b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["gifs", "shots"])
    ap.add_argument("--width", type=int, default=720, help="GIF 가로 픽셀")
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--colors", type=int, default=64, help="GIF 팔레트 색 수 (작을수록 가볍다)")
    a = ap.parse_args()
    global COLORS
    COLORS = a.colors
    for n in ("deck.html", "deck-motion.html"):
        if not (EX / n).exists():
            sys.exit(f"{n} 가 없습니다. 먼저 build_deck.py 로 예시를 빌드하세요")
    if a.only != "shots":
        print("GIF 녹화")
        make_gifs(a.width, a.fps)
    if a.only != "gifs":
        print("스크린샷")
        make_shots(1280)


if __name__ == "__main__":
    main()
