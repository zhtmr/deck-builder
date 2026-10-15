#!/usr/bin/env python3
"""
render_check.py — 생성된 장표를 헤드리스 브라우저로 열어 검수한다.

- 각 슬라이드의 마지막 스텝 상태를 PNG 로 저장 (에이전트가 직접 열어보고 겹침/잘림 확인)
- 콘솔 에러, 텍스트 넘침(슬라이드 밖으로 나간 요소) 자동 탐지
- --pdf 옵션으로 인쇄용 PDF 도 생성

필요: pip install playwright && python -m playwright install chromium
사용: python3 render_check.py out/deck.html --shots out/shots [--pdf out/deck.pdf] [--slides 3,5]
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--shots", type=Path, default=None, help="스크린샷 저장 폴더")
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--slides", default="", help="쉼표로 구분한 슬라이드 번호(1부터). 비우면 전체")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없습니다: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        sys.exit(2)

    url = a.html.resolve().as_uri()
    problems, warnings = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        # CDN(폰트/코드 하이라이트) 로드 실패는 오프라인 환경에서 정상 → 경고로만 기록
        pg.on("console", lambda m: m.type == "error" and (
            warnings if "Failed to load resource" in m.text else problems).append(f"console: {m.text}"))
        pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        pg.goto(url + "?still=1")
        pg.wait_for_timeout(400)
        n = pg.evaluate("deck.count")
        want = [int(x) for x in a.slides.split(",") if x.strip()] or list(range(1, n + 1))
        if a.shots:
            a.shots.mkdir(parents=True, exist_ok=True)
        for i in want:
            steps = pg.evaluate(f"deck.steps({i-1})")
            pg.evaluate(f"deck.go({i-1}, {steps}, true)")
            pg.wait_for_timeout(250)
            # 넘침 검사: 활성 슬라이드 안에서 슬라이드 경계를 벗어난 텍스트 요소
            over = pg.evaluate(
                """() => {
                const s = document.querySelector('.slide.active'); const R = s.getBoundingClientRect();
                const bad = [];
                s.querySelectorAll('h1,h2,h3,li,p,.stat,.code,.col,.steps li,.term,.trow,.bcard,.tl-item').forEach(el => {
                  const r = el.getBoundingClientRect();
                  if (r.width === 0) return;
                  if (r.right > R.right + 2 || r.bottom > R.bottom + 2) bad.push((el.textContent||'').trim().slice(0,40));
                  if (el.scrollHeight > el.clientHeight + 4 && getComputedStyle(el).overflow === 'hidden') bad.push('잘림: ' + (el.textContent||'').trim().slice(0,40));
                });
                const ol = s.querySelector('.steps ol');
                if (ol && ol.scrollHeight > ol.clientHeight + 4) bad.push('플로우 단계 목록이 길어 스크롤됨(단계 수를 줄이거나 note 를 짧게)');
                return bad;
            }"""
            )
            for o in over:
                (warnings if o.startswith("플로우") else problems).append(f"slide {i}: {o}")
            if a.shots:
                pg.screenshot(path=str(a.shots / f"slide-{i:02d}.png"))
        if a.pdf:
            pg.goto(url + "?still=1")
            pg.wait_for_timeout(400)
            pg.emulate_media(media="print")
            pg.pdf(path=str(a.pdf), width="1600px", height="900px", print_background=True)
        b.close()

    print(json.dumps({"slides": n, "checked": want, "problems": problems, "warnings": sorted(set(warnings))}, ensure_ascii=False, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
