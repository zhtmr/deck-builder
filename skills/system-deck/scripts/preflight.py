#!/usr/bin/env python3
"""
preflight.py — 장표를 만들기 전에 환경을 한 번에 점검한다.

무엇이 있고 없는지, 없으면 어떻게 설치하는지, 그래서 이번 작업에서 **쓸 수 있는 경로**가 무엇인지 보여 준다.
결과의 "쓸 수 있는 경로"를 1단계 계획에 반영한다(예: 검수 불가 → 5단계 검수·비평을 건너뛴다고 미리 알림,
오프라인 → scene 라이브러리를 .deck/vendor/ 에 내장하거나 scene 을 쓰지 않음).

사용: python3 preflight.py [--offline] [--json]
  --offline  네트워크(CDN) 검사를 건너뛴다
종료 코드: 0 = 장표를 만들 수 있음(선택 기능이 없어도), 1 = 필수 조건(Python 3.9+) 미달
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.request

# 장표가 온라인일 때 불러오는 곳 (deck_template.html 의 폰트·코드 하이라이트, build_deck.py 의 LIBS)
CDNS = {
    "cdn.jsdelivr.net": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css",
    "cdnjs.cloudflare.com": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js",
}


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def chromium_ok() -> tuple[bool, str]:
    """playwright 가 있고 chromium 을 실제로 띄울 수 있는지. 모듈만 있고 브라우저가 없는 경우가 흔하다."""
    if not has_module("playwright"):
        return False, "playwright 모듈 없음"
    code = ("from playwright.sync_api import sync_playwright\n"
            "with sync_playwright() as p:\n    b = p.chromium.launch(); b.close()")
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "chromium 실행이 60초 안에 끝나지 않음"
    if r.returncode == 0:
        return True, "chromium 실행 확인"
    err = (r.stderr.strip().splitlines() or ["알 수 없는 오류"])
    msg = next((l for l in err if "Executable doesn't exist" in l or "Error" in l), err[-1])
    return False, msg.strip()[:160]


def reachable(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "deck-builder-preflight"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 400
    except Exception:
        return False


def check(offline: bool) -> dict:
    items = []

    def add(key, ok, need, what, fix="", detail=""):
        items.append({"key": key, "ok": None if ok is None else bool(ok), "need": need, "what": what, "fix": fix, "detail": detail})

    py_ok = sys.version_info >= (3, 9)
    add("python", py_ok, "필수", "빌드·스캔·인제스천", "Python 3.9 이상 설치",
        f"{sys.version_info.major}.{sys.version_info.minor}")
    add("git", shutil.which("git"), "권장", "git 이력 → story.json (workflow-historian)", "git 설치")
    ok, detail = chromium_ok()
    add("playwright", ok, "권장", "검수 스크린샷·시트, 비평, PDF·PPTX 내보내기",
        "pip install playwright && python -m playwright install chromium", detail)
    add("python-pptx", has_module("pptx"), "선택", "PPTX 내보내기", "pip install python-pptx")
    add("markitdown", has_module("markitdown"), "선택", "PDF·PPTX·DOCX·XLSX 문서 입력", 'pip install "markitdown[all]"')
    add("pyhwp", shutil.which("hwp5txt"), "선택", "바이너리 .hwp 입력 (표는 사라짐 — .hwpx 권장)", "pip install pyhwp")
    add("pyyaml", has_module("yaml"), "선택", "docker-compose 정밀 파싱", "pip install pyyaml")
    if offline:
        add("cdn", None, "선택", "Pretendard 폰트·코드 하이라이트·scene 라이브러리(gsap, three)", "", "검사 건너뜀(--offline)")
    else:
        down = [h for h, u in CDNS.items() if not reachable(u)]
        add("cdn", not down, "선택", "Pretendard 폰트·코드 하이라이트·scene 라이브러리(gsap, three)",
            "발표 환경이 오프라인이면 scene 라이브러리를 .deck/vendor/ 에 받아 내장",
            "연결 실패: " + ", ".join(down) if down else "연결 확인")
    return {"ok": py_ok, "items": items, "paths": paths({i["key"]: i["ok"] for i in items}, offline)}


def paths(ok: dict, offline: bool) -> list[str]:
    """이번 작업에서 쓸 수 있는 경로 (SKILL.md 단계 기준)."""
    out = []
    if ok["playwright"]:
        out.append("5단계 검수·시트·5-b 비평: 가능")
    else:
        out.append("5단계 검수·시트·5-b 비평: 불가 — 빌드 린트(--strict)와 deck-reviewer 만으로 진행하고, 검수·비평을 건너뛰었다고 보고한다")
    out.append("7단계 PDF: " + ("가능" if ok["playwright"] else "브라우저 인쇄(Ctrl+P)로 안내"))
    out.append("7단계 PPTX: " + ("가능" if ok["playwright"] and ok["python-pptx"] else "불가 — 필요하면 설치 명령을 안내"))
    docs = [".hwpx", ".md"] + ([".pdf", ".pptx", ".docx", ".xlsx"] if ok["markitdown"] else []) + ([".hwp"] if ok["pyhwp"] else [])
    out.append("2-b 문서 입력: " + " ".join(docs) + ("" if ok["markitdown"] else " (PDF·PPTX·DOCX·XLSX 는 markitdown 필요)"))
    out.append("3단계 git 이력: " + ("가능" if ok["git"] else "불가 — story.json 은 README·문서·코드 주석에서만 모은다"))
    if offline:
        out.append("scene·코드 하이라이트: 네트워크 미확인 — 발표 환경이 오프라인이면 라이브러리를 .deck/vendor/ 에 내장")
    elif ok["cdn"]:
        out.append("scene·코드 하이라이트: CDN 사용 가능 (발표장이 오프라인이면 .deck/vendor/ 내장 권장)")
    else:
        out.append("scene·코드 하이라이트: CDN 불가 — scene 은 vendor 내장 라이브러리로만, 코드는 무채색, 폰트는 시스템 폰트로 보인다")
    return out


def main():
    ap = argparse.ArgumentParser(description="deck-builder 환경 점검")
    ap.add_argument("--offline", action="store_true", help="CDN 연결 검사를 건너뜀")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    a = ap.parse_args()
    res = check(a.offline)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        mark = {True: "✓", False: "✗", None: "·"}
        for i in res["items"]:
            line = f"{mark[i['ok']]} {i['key']:<12} [{i['need']}] {i['what']}"
            if i["detail"]:
                line += f" — {i['detail']}"
            print(line)
            if i["ok"] is False and i["fix"]:
                print(f"    설치: {i['fix']}")
        print("\n쓸 수 있는 경로")
        for p in res["paths"]:
            print("  -", p)
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
