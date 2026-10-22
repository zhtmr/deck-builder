#!/usr/bin/env python3
"""
check_deck.py — 평가 실행이 끝난 .deck/ 폴더를 보고 evals.json 의 자동 판정 항목을 검사한다.

사용: python3 evals/check_deck.py <대상 저장소>/.deck [--slides 9-12] [--no-code] [--doc-only] [--repo <대상 저장소>] [--json]

  --slides A-B   슬라이드 수 범위 (storytelling.md 6절 분량표)
  --no-code      code 슬라이드가 없어야 한다 (비개발 청중)
  --doc-only     문서만 입력: model 노드가 비어 있고 topology/flow 가 없어야 한다
  --repo PATH    대상 저장소의 .deck/ 밖 파일이 바뀌지 않았는지 git 으로 확인

종료 코드: 0 = 모든 항목 통과, 1 = 하나 이상 실패
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "system-deck" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_deck as bd  # noqa: E402

PLAIN = re.compile(r"\*\*|`")


def strict_build(deck_path: Path) -> tuple[bool, str]:
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = bd.build(deck_path, None, True, strict=True)
    except Exception as e:   # DeckError, JSON 오류 등
        return False, str(e)[:200]
    lines = [l.strip() for l in err.getvalue().splitlines() if l.strip().startswith("-")]
    return rc == 0, f"{len(lines)}건: " + " / ".join(lines[:3]) if lines else "경고 없음"


def check(deck_dir: Path, slides: str = "", no_code: bool = False, doc_only: bool = False,
          repo: Path | None = None) -> list[dict]:
    res: list[dict] = []

    def add(key, ok, detail=""):
        res.append({"key": key, "ok": bool(ok), "detail": detail})

    outline = deck_dir / "outline.md"
    text = outline.read_text(encoding="utf-8") if outline.exists() else ""
    add("outline", "핵심 메시지" in text and "|" in text,
        "outline.md 에 핵심 메시지와 제목 표" if text else "outline.md 없음")

    dj = deck_dir / "deck.json"
    if not dj.exists():
        add("deck_json", False, "deck.json 없음")
        return res
    deck = json.loads(dj.read_text(encoding="utf-8-sig"))
    ss = deck.get("slides", [])
    types = [s.get("type") for s in ss]
    ok, detail = strict_build(dj)
    add("strict_build", ok, detail)

    missing = [s["title"] for s in ss
               if s.get("title") and s.get("type") not in ("title", "end")
               and PLAIN.sub("", s["title"]).strip() not in PLAIN.sub("", text)]
    add("titles_from_outline", not missing, "아웃라인에 없는 제목: " + ", ".join(missing[:3]) if missing else "")

    add("end_asks", bool(ss) and types[-1] == "end" and bool(ss[-1].get("asks")),
        f"마지막 장: {types[-1] if ss else '없음'}")
    if slides:
        lo, hi = (int(x) for x in slides.split("-"))
        add("slide_count", lo <= len(ss) <= hi, f"{len(ss)}장 (기대 {lo}~{hi})")
    if no_code:
        n = types.count("code")
        add("no_code", n == 0, f"code 슬라이드 {n}장")
    if doc_only:
        model = deck.get("model")
        if isinstance(model, str):
            model = json.loads((dj.parent / model).read_text(encoding="utf-8-sig"))
        bad = [t for t in types if t in ("topology", "flow")]
        add("doc_only", not (model or {}).get("nodes") and not bad,
            f"노드 {len((model or {}).get('nodes', []))}개, topology/flow {len(bad)}장")

    out = deck_dir / "out"
    add("html", (out / "deck.html").exists(), str(out / "deck.html"))
    sheets = sorted(out.glob("sheet*.png"))
    add("sheets", bool(sheets), f"{len(sheets)}장")

    crit = sorted(deck_dir.glob("critique_*.md"))
    add("critique", bool(crit), f"{len(crit)}개")
    # 독립 비평 절에 메인이 옮겨 적은 내용이 있어야 한다(양식의 괄호 안내문만 있으면 실패)
    body = "\n".join(p.read_text(encoding="utf-8") for p in crit)
    sec = body.split("독립 비평", 1)[1] if "독립 비평" in body else ""
    filled = [l for l in sec.splitlines()[1:] if l.strip().startswith(("-", "|")) and "옮겨 적는다" not in l]
    add("independent_critique", bool(filled), "deck-critic 판정 기록" if filled else "독립 비평 기록 없음")

    blob = json.dumps(ss, ensure_ascii=False)
    n = blob.count("[확인 필요")
    add("placeholders_reported", True, f"[확인 필요] {n}곳 — 보고에 목록이 있는지는 사람이 확인")

    if repo:
        r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
        changed = [l[3:] for l in r.stdout.splitlines()
                   if not l[3:].startswith(".deck/")]
        add("repo_untouched", r.returncode == 0 and not changed,
            "바뀐 파일: " + ", ".join(changed[:5]) if changed else "")
    return res


def main():
    ap = argparse.ArgumentParser(description="평가 실행 결과(.deck/) 자동 판정")
    ap.add_argument("deck_dir", type=Path)
    ap.add_argument("--slides", default="")
    ap.add_argument("--no-code", action="store_true")
    ap.add_argument("--doc-only", action="store_true")
    ap.add_argument("--repo", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = check(a.deck_dir, a.slides, a.no_code, a.doc_only, a.repo)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for r in res:
            print(f"{'✓' if r['ok'] else '✗'} {r['key']:<22} {r['detail']}")
        print(f"\n{sum(r['ok'] for r in res)}/{len(res)} 통과")
    sys.exit(0 if all(r["ok"] for r in res) else 1)


if __name__ == "__main__":
    main()
