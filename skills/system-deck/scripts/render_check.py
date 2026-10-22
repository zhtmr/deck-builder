#!/usr/bin/env python3
"""
render_check.py — 생성된 장표를 헤드리스 브라우저로 열어 검수한다.

- 각 슬라이드의 마지막 스텝 상태를 PNG 로 저장 (에이전트가 직접 열어보고 겹침/잘림 확인)
- --sheet: 슬라이드 전체를 라벨 붙은 격자 한 장으로 (Read 한 번으로 덱 전체 리듬·밀도 확인)
- --step-sheet: 슬라이드마다 스텝 0→N 을 한 줄로 (중간 스텝의 겹침·빈 화면 확인)
- 콘솔 에러, 텍스트 넘침(슬라이드 밖으로 나간 요소) 자동 탐지
- --pdf 옵션으로 인쇄용 PDF 도 생성

시트는 브라우저로 합성하므로 playwright 외 의존성이 없다. 칸이 --per 개를 넘으면 sheet_01.png, sheet_02.png … 로 나눈다.

필요: pip install playwright && python -m playwright install chromium
사용: python3 render_check.py out/deck.html --shots out/shots [--sheet out/sheet.png] [--step-sheet out/steps.png]
                              [--pdf out/deck.pdf] [--slides 3,5]
"""
import argparse
import base64
import html
import json
import sys
from pathlib import Path

W, H = 1600, 900
STEP_COLS = 6          # 스텝 시트 한 줄의 최대 칸 수. 스텝이 더 많으면 처음·끝을 포함해 고르게 뽑는다


def pick_steps(n: int, cols: int = STEP_COLS) -> list[int]:
    """스텝 0..n 가운데 처음과 끝을 포함해 최대 cols 개를 고르게 고른다."""
    if n + 1 <= cols:
        return list(range(n + 1))
    return sorted({round(i * n / (cols - 1)) for i in range(cols)})


def paths(out: Path, pages: int) -> list[Path]:
    if pages <= 1:
        return [out]
    return [out.with_name(f"{out.stem}_{k:02d}{out.suffix}") for k in range(1, pages + 1)]


def chunks(xs: list, n: int) -> list[list]:
    return [xs[i:i + n] for i in range(0, len(xs), n)] or [[]]


def sheet_html(rows: list[dict], cols: int, thumb: int) -> str:
    """rows: [{"label": str, "cells": [(png bytes, 칸 라벨)]}]. 라벨이 있는 줄은 머리글로 한 줄을 차지한다."""
    th = round(thumb * H / W)
    css = (
        "*{box-sizing:border-box;margin:0}"
        "body{background:#1b1d22;color:#e8eaf0;font:15px/1.3 system-ui,'Noto Sans CJK KR','Apple SD Gothic Neo',sans-serif;padding:16px}"
        f".grid{{display:grid;grid-template-columns:repeat({cols},{thumb}px);gap:14px 12px}}"
        ".row{grid-column:1/-1;font-weight:700;font-size:16px;padding-top:6px;border-top:1px solid #3a3f4b}"
        f".cell img{{display:block;width:{thumb}px;height:{th}px;border:1px solid #3a3f4b}}"
        ".cell div{margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#c3c8d4}"
    )
    parts = []
    for r in rows:
        if r.get("label"):
            parts.append(f'<div class="row">{html.escape(r["label"])}</div>')
        for png, label in r["cells"]:
            src = "data:image/png;base64," + base64.b64encode(png).decode()
            parts.append(f'<div class="cell"><img src="{src}"><div>{html.escape(label)}</div></div>')
    return f'<!doctype html><meta charset="utf-8"><style>{css}</style><div class="grid">{"".join(parts)}</div>'


def save_sheet(browser, rows: list[dict], cols: int, thumb: int, out: Path) -> None:
    pg = browser.new_page(viewport={"width": cols * (thumb + 12) + 32, "height": 100})   # full_page 라 내용 높이만큼 늘어난다
    pg.set_content(sheet_html(rows, cols, thumb))
    out.parent.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(out), full_page=True)
    pg.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--shots", type=Path, default=None, help="스크린샷 저장 폴더")
    ap.add_argument("--sheet", type=Path, default=None, help="슬라이드 전체 격자 PNG")
    ap.add_argument("--step-sheet", type=Path, default=None, help="슬라이드별 스텝 0→N 줄 PNG (스텝 있는 슬라이드만)")
    ap.add_argument("--cols", type=int, default=3, help="--sheet 의 열 수")
    ap.add_argument("--per", type=int, default=12, help="--sheet 한 장의 칸 수 (--step-sheet 는 줄 수의 기준 per/2)")
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--slides", default="", help="쉼표로 구분한 슬라이드 번호(1부터). 비우면 전체")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없습니다: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        sys.exit(2)

    url = a.html.resolve().as_uri()
    problems, warnings, sheets = [], [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
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

        def show(i, k):
            pg.evaluate(f"deck.go({i-1}, {k}, true)")
            if not pg.evaluate("deck.ready ? deck.ready() : true"):   # scene 슬라이드: 라이브러리 로드·초기화 대기
                warnings.append(f"slide {i}: 장면 준비가 8초 안에 끝나지 않음")
            pg.wait_for_timeout(250)

        def meta():
            return pg.evaluate("""() => { const s = document.querySelector('.slide.active');
                const t = (s.className.match(/\\bt-(\\S+)/) || [])[1] || '';
                const h = s.querySelector('h1,h2,p.statement,blockquote');
                return [t, (h ? h.textContent : '').replace(/\\s+/g, ' ').trim()]; }""")

        finals, strips = [], []
        for i in want:
            steps = pg.evaluate(f"deck.steps({i-1})")
            if a.step_sheet and steps > 0:
                cells = []
                for k in pick_steps(steps):
                    show(i, k)
                    cells.append((pg.screenshot(), f"스텝 {k}/{steps}"))
                kind, title = meta()
                strips.append({"label": f"{i:02d} · {kind} · {title}", "cells": cells})
            show(i, steps)
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
            if a.shots or a.sheet:
                png = pg.screenshot()
                if a.shots:
                    (a.shots / f"slide-{i:02d}.png").write_bytes(png)
                kind, title = meta()
                finals.append((png, f"{i:02d} · {kind} · {title}" + (f" · 스텝 {steps}" if steps else "")))

        if a.sheet:
            pages = chunks(finals, max(1, a.per))
            for out, cells in zip(paths(a.sheet, len(pages)), pages):
                save_sheet(b, [{"cells": cells}], max(1, a.cols), 480, out)
                sheets.append(str(out))
        if a.step_sheet:
            if strips:
                pages = chunks(strips, max(1, a.per // 2))
                for out, rows in zip(paths(a.step_sheet, len(pages)), pages):
                    save_sheet(b, rows, STEP_COLS, 300, out)
                    sheets.append(str(out))
            else:
                warnings.append("step-sheet: 스텝이 있는 슬라이드가 없어 만들지 않음")
        if a.pdf:
            pg.goto(url + "?still=1")
            pg.wait_for_timeout(400)
            # scene 장면은 한 번 보여 줘야 그려지므로 전부 거쳐 간다
            pg.evaluate("""async () => { for (let i = 0; i < deck.count; i++){ deck.go(i, deck.steps(i), true); await deck.ready(); } deck.go(0, 0, true); }""")
            pg.emulate_media(media="print")
            pg.pdf(path=str(a.pdf), width="1600px", height="900px", print_background=True)
        b.close()

    res = {"slides": n, "checked": want, "problems": problems, "warnings": sorted(set(warnings))}
    if sheets:
        res["sheets"] = sheets
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
