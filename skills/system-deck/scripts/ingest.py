#!/usr/bin/env python3
"""
ingest.py — 문서(HWPX/HWP/PDF/PPTX/DOCX/XLSX/MD/TXT)를 Markdown 으로 변환하고 표를 구조화해 추출한다.

- HWPX 는 표준 라이브러리(zipfile + xml)만으로 직접 파싱한다 (문단·표·중첩 표).
- HWP(바이너리)는 pyhwp 의 `hwp5txt` 가 있으면 사용한다. 표는 보존되지 않으므로 HWPX/PDF 로 저장해 쓰길 권장.
- PDF/PPTX/DOCX/XLSX 는 `markitdown` 이 설치돼 있으면 사용한다 (pip install "markitdown[all]").
- 디렉토리를 주면 안에 있는 문서 파일을 모두 처리한다 (.git, node_modules, .deck 제외).

산출물 (기본 <out>/ = ./.deck):
    source.md           변환된 본문. 표 앞에 `> [표 N · 파일명]` 표식이 붙는다 (출처 인용용)
    source-tables.json  표 목록: 헤더/행/숫자 열/추천 슬라이드 타입

사용법:
    python3 ingest.py 기획서.hwpx 보고서.pdf -o .deck
    python3 ingest.py ./docs -o .deck
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MARKITDOWN_EXT = {".pdf", ".pptx", ".docx", ".xlsx", ".xls", ".html", ".htm", ".csv"}
TEXT_EXT = {".md", ".markdown", ".txt"}
DOC_EXT = MARKITDOWN_EXT | TEXT_EXT | {".hwpx", ".hwp"}
SKIP_DIRS = {".git", "node_modules", ".deck", ".venv", "venv", "__pycache__", "dist", "build"}


class IngestError(Exception):
    pass


# ----------------------------------------------------------------------------
# HWPX
# ----------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _own_text(p: ET.Element) -> str:
    """문단 안의 텍스트. 표(tbl) 내부는 들어가지 않는다."""
    out: list[str] = []

    def walk(el: ET.Element):
        for c in el:
            name = _local(c.tag)
            if name in ("tbl", "ctrl"):   # ctrl: 입력 안내 필드·머리말/꼬리말·각주 등 본문이 아닌 부속 내용
                continue
            if name == "t":
                out.append("".join(c.itertext()))
            elif name == "tab":
                out.append(" ")
            elif name in ("lineBreak", "br"):
                out.append(" ")
            else:
                walk(c)

    walk(p)
    return re.sub(r"[ \t ]+", " ", "".join(out)).strip()


def _tables_in(p: ET.Element) -> list[ET.Element]:
    found: list[ET.Element] = []

    def walk(el: ET.Element):
        for c in el:
            if _local(c.tag) == "tbl":
                found.append(c)
            else:
                walk(c)

    walk(p)
    return found


def _cell_text(tc: ET.Element) -> str:
    """셀 안의 모든 문단(중첩 표 포함)을 한 줄로."""
    parts: list[str] = []

    def walk(el: ET.Element):
        for c in el:
            n = _local(c.tag)
            if n == "p":
                t = _own_text(c)
                if t:
                    parts.append(t)
                for tb in _tables_in(c):
                    parts.append(" / ".join(" ".join(r) for r in _table_rows(tb)))
            elif n != "ctrl":
                walk(c)

    walk(tc)
    return " ".join(parts).replace("|", "\\|")


def _table_rows(tbl: ET.Element) -> list[list[str]]:
    """표를 2차원 격자로. 병합 셀은 cellAddr/cellSpan 으로 제자리에 놓는다.
    가로 병합은 첫 칸에만 글을 두고, 세로 병합은 아래 칸에도 같은 글을 반복한다(행 라벨 유지)."""
    cells: list[tuple[ET.Element, tuple | None, tuple]] = []
    for tr in tbl:
        if _local(tr.tag) != "tr":
            continue
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            addr, span = None, (1, 1)
            for c in tc:
                n = _local(c.tag)
                if n == "cellAddr":
                    addr = (int(c.get("colAddr", 0)), int(c.get("rowAddr", 0)))
                elif n == "cellSpan":
                    span = (max(1, int(c.get("colSpan", 1))), max(1, int(c.get("rowSpan", 1))))
            cells.append((tc, addr, span))
    if not cells:
        return []
    if all(a is not None for _, a, _ in cells):
        R = max(a[1] + s[1] for _, a, s in cells)
        C = max(a[0] + s[0] for _, a, s in cells)
        if R * C <= 200_000:
            grid = [[""] * C for _ in range(R)]
            for tc, (c0, r0), (cs, rs) in cells:
                text = _cell_text(tc)
                grid[r0][c0] = text
                for k in range(1, rs):
                    if r0 + k < R:
                        grid[r0 + k][c0] = text
            return [r for r in grid if any(x for x in r)] or grid[:1]
    # 주소 정보가 없으면 tc 순서대로
    rows: list[list[str]] = []
    for tr in tbl:
        if _local(tr.tag) == "tr":
            row = [_cell_text(tc) for tc in tr if _local(tc.tag) == "tc"]
            if row:
                rows.append(row)
    return rows


def _rows_to_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * w) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def parse_hwpx(path: Path) -> str:
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise IngestError(f"{path.name}: HWPX(zip)가 아닙니다 ({e}). .hwp 라면 확장자를 확인하세요") from e
    with z:
        secs = sorted(
            (n for n in z.namelist() if re.search(r"(^|/)section\d+\.xml$", n, re.I)),
            key=lambda n: int(re.search(r"(\d+)\.xml$", n, re.I).group(1)),
        )
        if not secs:
            raise IngestError(f"{path.name}: Contents/section*.xml 이 없습니다 (암호화된 문서일 수 있음)")
        out: list[str] = []
        for name in secs:
            root = ET.fromstring(z.read(name))
            for p in root.iter():
                if _local(p.tag) != "p" or _is_nested_p(root, p):
                    continue
                t = _own_text(p)
                if t:
                    out.append(t)
                for tb in _tables_in(p):
                    rows = _table_rows(tb)
                    if rows and (len(rows) == 1 or max(len(r) for r in rows) == 1):
                        # 한 줄/한 칸짜리 표는 데이터 표가 아니라 제목 상자·강조 상자로 쓰인 것 → 문단으로
                        out.extend(" ".join(x for x in dict.fromkeys(r) if x) for r in rows if any(r))
                        continue
                    md = _rows_to_md(rows)
                    if md:
                        out.append("\n" + md + "\n")
    return "\n\n".join(out)


_PARENT_CACHE: dict[int, dict[ET.Element, ET.Element]] = {}


def _is_nested_p(root: ET.Element, p: ET.Element) -> bool:
    """표 셀 안의 문단은 표 처리에서 이미 읽었으므로 최상위 순회에서 건너뛴다."""
    pm = _PARENT_CACHE.get(id(root))
    if pm is None:
        pm = {c: par for par in root.iter() for c in par}
        _PARENT_CACHE[id(root)] = pm
    cur = pm.get(p)
    while cur is not None:
        if _local(cur.tag) in ("tc", "tbl", "ctrl"):
            return True
        cur = pm.get(cur)
    return False


# ----------------------------------------------------------------------------
# 그 외 포맷
# ----------------------------------------------------------------------------
def parse_hwp(path: Path) -> str:
    exe = shutil.which("hwp5txt")
    if not exe:
        raise IngestError(
            f"{path.name}: 바이너리 .hwp 는 pyhwp 가 필요합니다 (pip install pyhwp). "
            "표 구조를 살리려면 한글에서 .hwpx 또는 PDF 로 저장해 다시 넣으세요")
    r = subprocess.run([exe, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise IngestError(f"{path.name}: hwp5txt 실패: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def parse_markitdown(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise IngestError(f"{path.name}: markitdown 이 필요합니다 (pip install \"markitdown[all]\")") from e
    return MarkItDown().convert(str(path)).text_content.strip()


def parse_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return path.read_text(encoding=enc).strip()
        except UnicodeDecodeError:
            continue
    raise IngestError(f"{path.name}: 인코딩을 알 수 없습니다 (utf-8/cp949 아님)")


def convert(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".hwpx":
        return parse_hwpx(path)
    if ext == ".hwp":
        return parse_hwp(path)
    if ext in TEXT_EXT:
        return parse_text(path)
    if ext in MARKITDOWN_EXT:
        return parse_markitdown(path)
    raise IngestError(f"{path.name}: 지원하지 않는 확장자 '{ext}' (지원: {', '.join(sorted(DOC_EXT))})")


# ----------------------------------------------------------------------------
# 표 추출 (Markdown 파이프 테이블)
# ----------------------------------------------------------------------------
_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_NUM = re.compile(r"^[+\-−]?\s*[\d,]+(\.\d+)?\s*(%|배|건|명|원|억|만|천|ms|s|sec|초|분|시간|일|개|회|x|X|k|K|M|G|B|req/s)?$")
_PERIOD = re.compile(r"^(\d{4}([.\-/년]\s*\d{1,2})?|\d{1,2}월|[1-4]Q|Q[1-4]|\d{4}\s*Q[1-4]|\d+주차|\d+단계|Phase\s*\d+)")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur = [], ""
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if s[i] == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += s[i]
        i += 1
    cells.append(cur.strip())
    return cells


_ID_HDR = re.compile(r"번호|순번|연번|순위|계급|등급|코드|^no\.?$|^id$", re.I)   # 숫자처럼 보여도 지표가 아닌 식별자 열


def _suggest(header: list[str], rows: list[list[str]]) -> tuple[str, list[int], float]:
    """(추천 슬라이드 타입, 숫자 지표 열, 빈 칸 비율). 크고 성긴 표는 변환하지 않고 발췌만 권한다."""
    ncols = len(header)
    cells = [c for r in rows for c in r]
    empty = round(sum(1 for c in cells if not c) / len(cells), 2) if cells else 0.0
    num_cols = [c for c in range(ncols)
                if rows and not _ID_HDR.search(header[c].replace(" ", ""))
                and sum(bool(_NUM.match(r[c])) for r in rows if c < len(r)) >= max(1, len(rows) * 0.6)]
    if len(rows) > 12 or ncols > 8 or empty > 0.4:
        return "excerpt", num_cols, empty      # 예산표·코드표 등. 슬라이드에는 핵심 행 3~4개만 발췌
    first = [r[0] for r in rows if r]
    if first and sum(bool(_PERIOD.match(x)) for x in first) >= max(2, len(first) * 0.6):
        return "timeline", num_cols, empty
    if num_cols and len(rows) <= 4:
        return "stats", num_cols, empty
    if num_cols:
        return "stats(상위 4행 선별)", num_cols, empty
    if ncols == 2 and len(rows) <= 6:
        return "split", num_cols, empty
    if len(rows) <= 4:
        return "bento", num_cols, empty
    return "bullets(요약)", num_cols, empty


def extract_tables(md: str, source: str, start_no: int = 1) -> tuple[str, list[dict]]:
    """본문 안의 파이프 테이블을 찾아 `> [표 N · source]` 표식을 앞에 붙이고 구조화한다."""
    lines = md.split("\n")
    out: list[str] = []
    tables: list[dict] = []
    i, no = 0, start_no
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and _SEP.match(lines[i + 1]) and "|" in lines[i + 1]:
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                j += 1
            header = _split_row(lines[i])
            rows = [_split_row(x) for x in lines[i + 2:j]]
            kind, num_cols, empty = _suggest(header, rows)
            tables.append({"no": no, "source": source, "header": header, "rows": rows,
                           "numeric_cols": num_cols, "empty_ratio": empty, "suggest": kind})
            out.append(f"> [표 {no} · {source}]")
            out.extend(lines[i:j])
            no += 1
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), tables


# ----------------------------------------------------------------------------
# 진입점
# ----------------------------------------------------------------------------
def collect(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in inputs:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in DOC_EXT and not (set(f.relative_to(p).parts[:-1]) & SKIP_DIRS):
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            raise IngestError(f"경로가 없습니다: {p}")
    return files


def run(inputs: list[Path], out_dir: Path) -> int:
    files = collect(inputs)
    if not files:
        print("처리할 문서가 없습니다", file=sys.stderr)
        return 1
    sections: list[str] = []
    all_tables: list[dict] = []
    failed: list[str] = []
    for f in files:
        try:
            md = convert(f)
        except IngestError as e:
            failed.append(str(e))
            continue
        if not md.strip():
            failed.append(f"{f.name}: 추출된 텍스트가 없습니다 (스캔 이미지 PDF 일 수 있음 — OCR 필요)")
            continue
        md, tbls = extract_tables(md, f.name, len(all_tables) + 1)
        all_tables += tbls
        sections.append(f"# 📄 {f.name}\n\n{md}")
    if not sections:
        for m in failed:
            print("실패:", m, file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "source.md").write_text("\n\n---\n\n".join(sections) + "\n", encoding="utf-8")
    (out_dir / "source-tables.json").write_text(json.dumps(all_tables, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(s) for s in sections)
    print(f"문서 {len(sections)}/{len(files)}개 변환, 본문 {total:,}자, 표 {len(all_tables)}개 → {out_dir / 'source.md'}")
    for t in all_tables:
        print(f"  표 {t['no']} ({t['source']}): {len(t['rows'])}행 x {len(t['header'])}열 → 추천 {t['suggest']}")
    for m in failed:
        print("  건너뜀:", m, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description="문서를 Markdown 과 표 JSON 으로 변환")
    ap.add_argument("inputs", nargs="+", type=Path, help="문서 파일 또는 디렉토리")
    ap.add_argument("-o", "--out", type=Path, default=Path(".deck"), help="출력 폴더 (기본 ./.deck)")
    a = ap.parse_args()
    try:
        sys.exit(run(a.inputs, a.out))
    except IngestError as e:
        print("오류:", e, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
