#!/usr/bin/env python3
"""
build_deck.py — system-model.json + deck.json  ->  단일 HTML 발표 장표

- 외부 의존성 없음(Python 표준 라이브러리만). 결과 HTML도 오프라인에서 동작한다.
  (Pretendard 폰트, highlight.js 는 온라인일 때만 CDN 에서 불러오고 없으면 시스템 폰트/무채색으로 대체)
- 토폴로지는 Python 에서 계층 레이아웃을 계산해 SVG 로 내보내고, JS 가 애니메이션을 담당한다.

사용법:
    python3 build_deck.py deck.json -o out/deck.html
    python3 build_deck.py deck.json --validate-only
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# 상수
# ----------------------------------------------------------------------------
STAGE_W, STAGE_H = 1600, 900

KINDS = {
    # kind: (색, 표시 라벨, 기본 tier 힌트)
    "client":   ("#60a5fa", "CLIENT",   0),
    "gateway":  ("#a78bfa", "GATEWAY",  1),
    "service":  ("#34d399", "SERVICE",  2),
    "worker":   ("#2dd4bf", "WORKER",   2),
    "ai":       ("#f472b6", "AI / ML",  2),
    "job":      ("#38bdf8", "BATCH",    2),
    "queue":    ("#fbbf24", "QUEUE",    3),
    "db":       ("#fb923c", "DATABASE", 4),
    "cache":    ("#f87171", "CACHE",    4),
    "storage":  ("#facc15", "STORAGE",  4),
    "external": ("#94a3b8", "EXTERNAL", 5),
}

# type: (필수 필드, 선택 필드). 공통 필드(type, id, title, notes)는 모든 타입에 허용.
SLIDE_FIELDS: dict[str, tuple[set, set]] = {
    "title":    (set(), {"subtitle"}),
    "section":  ({"title"}, {"no", "subtitle"}),
    "bullets":  ({"bullets"}, {"reveal"}),
    "topology": (set(), {"flow", "focus", "nodes", "caption"}),
    "flow":     ({"flow"}, {"nodes", "description"}),
    "code":     (set(), {"code", "file", "lang", "start_line", "highlight", "points", "walk", "magic"}),
    "image":    ({"src"}, {"alt", "caption", "marks", "fit"}),
    "statement": ({"text"}, {"kicker", "subtitle"}),
    "quote":    ({"quote"}, {"by"}),
    "split":    ({"left", "right"}, set()),
    "stats":    ({"items"}, set()),
    "terminal": ({"items"}, {"window_title", "command", "summary"}),
    "bento":    ({"cards"}, set()),
    "timeline": ({"items"}, set()),
    "scene":    (set(), {"script", "script_file", "html", "css", "libs", "steps", "caption", "fallback", "full"}),
    "end":      (set(), {"subtitle", "asks"}),
}
SLIDE_TYPES = set(SLIDE_FIELDS)
COMMON_FIELDS = {"type", "id", "title", "notes", "transition", "fx"}
TRANSITIONS = {"slide-left", "slide-up", "zoom", "fade", "none"}   # 슬라이드 간 전환
FX = {"up", "left", "right", "scale", "fade"}                      # 스텝(클릭) 등장 프리셋
STATUS = {"OK": "ok", "WARN": "warn", "FAIL": "fail"}
THEMES = ("aurora", "dark", "light", "toss")
ACCENTS = {"aurora": "#8ab4ff", "dark": "#7dd3fc", "light": "#2563eb", "toss": "#3182f6"}
MAX_INLINE_BYTES = 3 * 1024 * 1024    # 이미지 한 장을 HTML 에 내장하는 한계 (넘으면 경고)
# scene 슬라이드가 이름으로 부를 수 있는 라이브러리: (module 여부, URL, 전역 이름). 버전은 고정한다.
LIBS = {
    "gsap":  (False, "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js", "gsap"),
    "three": (True,  "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js", None),
}
MAX_SCENE_STEPS = 20
BASE_DIR = Path(".")                  # build() 가 deck.json 위치로 설정한다 (이미지 상대 경로 기준)

# 텍스트 길이 한계 (공백 포함, 마크업 제외). 넘으면 린트 경고.
LIMITS = {"title": 28, "title_slide": 40, "bullet": 45, "card_body": 45, "detail": 45, "label": 40}

# 주제형 제목(슬라이드가 무슨 주제인지만 말하고 결론은 없는 제목). 주장형으로 바꾸라고 경고한다.
TOPIC_TITLES = {
    "개요", "소개", "배경", "목차", "문제", "문제점", "왜 만들었나", "목표", "아키텍처", "시스템 아키텍처",
    "전체 구성", "구성", "시스템 구성", "구조", "기술 스택", "요청 흐름", "흐름", "데이터 흐름", "주요 기능",
    "핵심 기능", "기능", "구현", "구현 과정", "구현 타임라인", "타임라인", "일정", "결과", "성과", "효과",
    "지표", "결론", "정리", "요약", "향후 계획", "향후 과제", "남은 과제", "다음 단계", "질의응답", "감사합니다",
}
# 주장형 제목을 요구하지 않는 타입 (장 구분·표지·인용·마무리)
TITLE_EXEMPT = {"title", "section", "statement", "quote", "end"}


class DeckError(Exception):
    pass


# ----------------------------------------------------------------------------
# 검증
# ----------------------------------------------------------------------------
def validate(model: dict, deck: dict) -> list[str]:
    errs: list[str] = []
    nodes = model.get("nodes") or []
    edges = model.get("edges") or []
    flows = model.get("flows") or []
    nid = set()
    for i, n in enumerate(nodes):
        if "id" not in n:
            errs.append(f"nodes[{i}]: id 없음")
            continue
        if n["id"] in nid:
            errs.append(f"nodes[{i}]: id 중복 '{n['id']}'")
        nid.add(n["id"])
        if n.get("kind", "service") not in KINDS:
            errs.append(f"node '{n['id']}': 알 수 없는 kind '{n.get('kind')}' (허용: {', '.join(KINDS)})")
    eid = set()
    for i, e in enumerate(edges):
        if "id" not in e:
            errs.append(f"edges[{i}]: id 없음")
            continue
        if e["id"] in eid:
            errs.append(f"edges[{i}]: id 중복 '{e['id']}'")
        eid.add(e["id"])
        for k in ("from", "to"):
            if e.get(k) not in nid:
                errs.append(f"edge '{e['id']}': {k}='{e.get(k)}' 노드가 없음")
    if deck.get("transition") and deck["transition"] not in TRANSITIONS:
        errs.append(f"deck.transition 은 {' | '.join(sorted(TRANSITIONS))}")
    fid = set()
    for f in flows:
        fid.add(f.get("id"))
        if not f.get("steps"):
            errs.append(f"flow '{f.get('id')}': steps 비어 있음")
        for j, s in enumerate(f.get("steps", [])):
            if s.get("edge") not in eid:
                errs.append(f"flow '{f.get('id')}' step {j+1}: edge '{s.get('edge')}' 없음")
    for i, s in enumerate(deck.get("slides", [])):
        t = s.get("type")
        if t not in SLIDE_TYPES:
            errs.append(f"slides[{i}]: 알 수 없는 type '{t}' (허용: {', '.join(sorted(SLIDE_TYPES))})")
        if t == "flow" and s.get("flow") not in fid:
            errs.append(f"slides[{i}] (flow): flow '{s.get('flow')}' 없음")
        if t == "topology" and s.get("flow") and s["flow"] not in fid:
            errs.append(f"slides[{i}] (topology): flow '{s.get('flow')}' 없음")
        for key in ("focus", "nodes"):
            for x in s.get(key, []) or []:
                if x not in nid:
                    errs.append(f"slides[{i}]: {key} 에 없는 노드 '{x}'")
        if t in SLIDE_FIELDS:
            errs += validate_slide(i, s)
    return errs


def validate_slide(i: int, s: dict) -> list[str]:
    """타입별 필수 필드와 내용 규칙. (알 수 없는 필드는 lint 의 경고로 다룬다)"""
    t = s["type"]
    req, _ = SLIDE_FIELDS[t]
    p = f"slides[{i}] ({t})"
    errs = [f"{p}: 필수 필드 '{k}' 없음" for k in sorted(req) if not s.get(k)]
    if s.get("transition") and s["transition"] not in TRANSITIONS:
        errs.append(f"{p}: transition 은 {' | '.join(sorted(TRANSITIONS))}")
    if s.get("fx") and s["fx"] not in FX:
        errs.append(f"{p}: fx 는 {' | '.join(sorted(FX))}")
    if t == "end" and "asks" in s:
        a = s["asks"]
        if not (isinstance(a, list) and 1 <= len(a) <= 3 and all(isinstance(x, str) and x.strip() for x in a)):
            errs.append(f"{p}: asks 는 문자열 1~3개 목록이어야 합니다")

    def items(key, lo, hi):
        v = s.get(key)
        if not isinstance(v, list):
            return []
        if not lo <= len(v) <= hi:
            errs.append(f"{p}: {key} 는 {lo}~{hi}개여야 합니다 (현재 {len(v)})")
        for j, x in enumerate(v):
            if not isinstance(x, dict):
                errs.append(f"{p}: {key}[{j}] 는 객체여야 합니다")
        return [x for x in v if isinstance(x, dict)]

    if t == "stats":
        for j, x in enumerate(items("items", 1, 6)):
            if x.get("value") in (None, ""):
                errs.append(f"{p}: items[{j}].value 없음")
            if "bar" in x and not (isinstance(x["bar"], (int, float)) and 0 <= x["bar"] <= 100):
                errs.append(f"{p}: items[{j}].bar 는 0~100 숫자")
    elif t == "terminal":
        for j, x in enumerate(items("items", 1, 7)):
            if not x.get("label"):
                errs.append(f"{p}: items[{j}].label 없음")
            if str(x.get("status", "OK")).upper() not in STATUS:
                errs.append(f"{p}: items[{j}].status 는 OK | WARN | FAIL")
            pr = x.get("progress", 100)
            if not (isinstance(pr, (int, float)) and 0 <= pr <= 100):
                errs.append(f"{p}: items[{j}].progress 는 0~100 숫자")
    elif t == "bento":
        for j, x in enumerate(items("cards", 2, 4)):
            if not x.get("title"):
                errs.append(f"{p}: cards[{j}].title 없음")
    elif t == "timeline":
        for j, x in enumerate(items("items", 2, 6)):
            if not (x.get("period") and x.get("title")):
                errs.append(f"{p}: items[{j}] 에 period 와 title 이 필요합니다")
    elif t == "image":
        for j, m in enumerate(s.get("marks") or []):
            b = m.get("box") if isinstance(m, dict) else None
            ok = (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)
                  and 0 <= b[0] and 0 <= b[1] and b[2] > 0 and b[3] > 0 and b[0] + b[2] <= 100 and b[1] + b[3] <= 100)
            if not ok:
                errs.append(f"{p}: marks[{j}].box 는 이미지 대비 % 로 [x, y, w, h] (x+w, y+h ≤ 100)")
        if s.get("fit") not in (None, "contain", "cover"):
            errs.append(f"{p}: fit 은 contain | cover")
    elif t == "code":
        magic = s.get("magic")
        if not s.get("code") and not magic:
            errs.append(f"{p}: code 또는 magic 중 하나가 필요합니다")
        if magic:
            if s.get("code") or s.get("walk"):
                errs.append(f"{p}: magic 은 code/walk 와 함께 쓸 수 없습니다")
            if not (isinstance(magic, list) and 2 <= len(magic) <= 8):
                errs.append(f"{p}: magic 은 코드 버전 2~8개 목록")
            else:
                for j, v in enumerate(magic):
                    if not (isinstance(v, dict) and v.get("code")):
                        errs.append(f"{p}: magic[{j}].code 없음")
            return errs
        start = int(s.get("start_line", 1))
        end = start + len(str(s.get("code", "")).rstrip("\n").split("\n")) - 1
        for j, w in enumerate(s.get("walk") or []):
            a, b = walk_range(w)
            if a is None or not (start <= a <= b <= end):
                errs.append(f"{p}: walk[{j}].lines 는 코드 줄 번호 범위({start}~{end}) 안의 [시작, 끝]")
    elif t == "scene":
        if bool(s.get("script")) == bool(s.get("script_file")):
            errs.append(f"{p}: script 또는 script_file 중 정확히 하나가 필요합니다")
        st = s.get("steps", 0)
        if not (isinstance(st, int) and not isinstance(st, bool) and 0 <= st <= MAX_SCENE_STEPS):
            errs.append(f"{p}: steps 는 0~{MAX_SCENE_STEPS} 정수")
        libs = s.get("libs", [])
        if not isinstance(libs, list):
            errs.append(f"{p}: libs 는 목록")
            libs = []
        for j, L in enumerate(libs):
            if isinstance(L, str):
                if L not in LIBS:
                    errs.append(f"{p}: libs[{j}] '{L}' 은 내장 라이브러리가 아닙니다 (내장: {', '.join(LIBS)}). "
                                "그 외는 {name, url} 또는 {name, src} 로 지정")
            elif not (isinstance(L, dict) and re.fullmatch(r"[A-Za-z_$][\w$]*", str(L.get("name", "")))
                      and bool(L.get("url")) != bool(L.get("src"))):
                errs.append(f"{p}: libs[{j}] 는 내장 이름 문자열이거나 {{name, url}} / {{name, src}} 객체 (name 은 JS 식별자)")
    return errs


def walk_range(w) -> tuple:
    ln = w.get("lines") if isinstance(w, dict) else None
    if isinstance(ln, int):
        return ln, ln
    if isinstance(ln, list) and len(ln) == 2 and all(isinstance(v, int) for v in ln):
        return ln[0], ln[1]
    return None, None


# ----------------------------------------------------------------------------
# 린트 (경고): 길이, 강조 남용, 근거 누락, 오타 필드
# ----------------------------------------------------------------------------
def plain(s) -> str:
    return re.sub(r"\*\*|`", "", str(s or ""))


def lint(deck: dict) -> list[str]:
    w: list[str] = []
    for i, s in enumerate(deck.get("slides", [])):
        t = s.get("type")
        if t not in SLIDE_FIELDS:
            continue
        p = f"slides[{i}] ({t})"
        req, opt = SLIDE_FIELDS[t]
        for k in s:
            if k not in req | opt | COMMON_FIELDS:
                w.append(f"{p}: 알 수 없는 필드 '{k}' (오타이거나 무시됨)")

        def long(text, limit, where):
            if len(plain(text)) > limit:
                w.append(f"{p}: {where} {len(plain(text))}자 > {limit}자: \"{plain(text)[:24]}…\"")

        long(s.get("title"), LIMITS["title_slide"] if t == "title" else LIMITS["title"], "제목")
        if t not in TITLE_EXEMPT and s.get("title"):
            tt = re.sub(r"[\s.!?·:]+$", "", plain(s["title"])).strip()
            if tt in TOPIC_TITLES or (len(tt.split()) <= 1 and len(tt) <= 8):
                w.append(f"{p}: 제목 \"{tt}\" 이 주제형입니다 — 이 장의 결론을 한 문장으로 (예: \"무거운 처리는 요청 경로 밖으로\")")
        if t == "end":
            asks = s.get("asks")
            if not asks:
                w.append(f"{p}: asks(청중에게 요청할 행동·다음 단계 1~3개) 없음 — 마지막 장은 요청으로 끝낸다")
            for a in asks or []:
                long(a, LIMITS["bullet"], "요청")
        for b in s.get("bullets") or []:
            long(b.get("text") if isinstance(b, dict) else b, LIMITS["bullet"], "불릿")
        for c in s.get("cards") or []:
            long(c.get("title"), LIMITS["label"], "카드 제목")
            long(c.get("body"), LIMITS["card_body"], "카드 본문")
        for x in s.get("items") or []:
            if not isinstance(x, dict):
                continue
            if t == "timeline":
                long(x.get("title"), LIMITS["label"], "타임라인 제목")
                long(x.get("detail"), LIMITS["detail"], "타임라인 설명")
            elif t == "stats":
                long(x.get("hint"), LIMITS["detail"], "지표 설명")
                if not x.get("source"):
                    w.append(f"{p}: 지표 '{plain(x.get('label'))[:16]}' 에 source 없음 (근거 없는 수치는 만들지 않는다)")
            elif t == "terminal":
                long(x.get("label"), LIMITS["label"], "항목")
                if not x.get("source"):
                    w.append(f"{p}: 항목 '{plain(x.get('label'))[:16]}' 에 source 없음 (실제로 확인된 상태만 [OK] 로 표시)")
        if t == "image":
            long(s.get("caption"), LIMITS["detail"], "캡션")
            if not s.get("alt"):
                w.append(f"{p}: alt(이미지 설명) 없음")
            for m in s.get("marks") or []:
                if isinstance(m, dict):
                    long(m.get("note"), 20, "하이라이트 라벨")
        if t == "scene":
            long(s.get("caption"), LIMITS["detail"], "캡션")
            remote = any(isinstance(L, str) or (isinstance(L, dict) and L.get("url")) for L in s.get("libs") or [])
            if remote and not s.get("fallback"):
                w.append(f"{p}: CDN 라이브러리를 쓰는데 fallback(오프라인일 때 보일 문구) 없음")
        if t == "code":
            for v in ([s.get("code", "")] + [m.get("code", "") for m in (s.get("magic") or []) if isinstance(m, dict)]):
                if len(str(v).rstrip("\n").split("\n")) > 20:
                    w.append(f"{p}: 코드가 20줄을 넘습니다")
                    break
        blob = json.dumps({k: v for k, v in s.items() if k != "notes"}, ensure_ascii=False)
        if blob.count("**") > 4:
            w.append(f"{p}: 강조(**)가 {blob.count('**') // 2}곳 — 슬라이드당 1~2곳 권장")
        if "[확인 필요" in blob or "[확인필요" in blob:
            w.append(f"{p}: [확인 필요] 자리표시가 남아 있음")
        if t not in ("section", "end") and not s.get("notes"):
            w.append(f"{p}: 발표자 노트(notes) 없음")
    return w


# ----------------------------------------------------------------------------
# 레이아웃 (계층형, 좌→우)
# ----------------------------------------------------------------------------
def layer_nodes(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    ids = [n["id"] for n in nodes]
    out = {i: [] for i in ids}
    for e in edges:
        if e["from"] != e["to"]:
            out[e["from"]].append(e["to"])

    # DFS 로 역방향(사이클) 간선 제거
    state: dict[str, int] = {}
    forward: dict[str, list[str]] = {i: [] for i in ids}

    def dfs(u: str):
        state[u] = 1
        for v in out[u]:
            if state.get(v) == 1:
                continue  # back edge
            forward[u].append(v)
            if v not in state:
                dfs(v)
        state[u] = 2

    # 입력 차수 0 → 클라이언트 → 나머지 순으로 시작해 자연스러운 방향을 얻는다
    indeg = {i: 0 for i in ids}
    for u in ids:
        for v in out[u]:
            indeg[v] += 1
    kind = {n["id"]: n.get("kind", "service") for n in nodes}
    order = sorted(ids, key=lambda i: (indeg[i] != 0, kind[i] != "client", ids.index(i)))
    sys.setrecursionlimit(10000)
    for u in order:
        if u not in state:
            dfs(u)

    layer = {i: 0 for i in ids}
    # 위상 정렬 후 longest path
    indeg2 = {i: 0 for i in ids}
    for u in ids:
        for v in forward[u]:
            indeg2[v] += 1
    q = [i for i in ids if indeg2[i] == 0]
    topo = []
    while q:
        u = q.pop(0)
        topo.append(u)
        for v in forward[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            indeg2[v] -= 1
            if indeg2[v] == 0:
                q.append(v)

    # 명시적 tier 가 있으면 우선
    explicit = {n["id"]: n["tier"] for n in nodes if isinstance(n.get("tier"), int)}
    layer.update(explicit)

    # 저장소/외부 시스템은 최소 자기 이웃보다 오른쪽에 두되 빈 계층은 압축
    used = sorted(set(layer.values()))
    remap = {v: i for i, v in enumerate(used)}
    return {k: remap[v] for k, v in layer.items()}


def order_layers(layers: dict[int, list[str]], edges: list[dict]) -> None:
    nbr: dict[str, set[str]] = {}
    for e in edges:
        nbr.setdefault(e["from"], set()).add(e["to"])
        nbr.setdefault(e["to"], set()).add(e["from"])
    keys = sorted(layers)
    for sweep in range(6):
        seq = keys[1:] if sweep % 2 == 0 else list(reversed(keys[:-1]))
        for L in seq:
            ref = L - 1 if sweep % 2 == 0 else L + 1
            if ref not in layers:
                continue
            pos = {n: i / max(1, len(layers[ref]) - 1) for i, n in enumerate(layers[ref])}
            cur = layers[L]

            def bary(n, i):
                ps = [pos[m] for m in nbr.get(n, ()) if m in pos]
                return sum(ps) / len(ps) if ps else i / max(1, len(cur) - 1)

            layers[L] = [n for _, n in sorted(((bary(n, i), i), n) for i, n in enumerate(cur))]


def layout(nodes: list[dict], edges: list[dict], W: int, H: int) -> dict[str, dict]:
    lay = layer_nodes(nodes, edges)
    layers: dict[int, list[str]] = {}
    for n in nodes:
        layers.setdefault(lay[n["id"]], []).append(n["id"])
    order_layers(layers, edges)
    L = max(layers) + 1 if layers else 1
    col_w = W / L
    nw = max(96, min(240, col_w * 0.74))
    pos = {}
    for li, ids in layers.items():
        k = len(ids)
        nh = 88 if k <= 5 else max(56, int((H - 40) / k) - 18)
        gap = H / k
        for j, n in enumerate(ids):
            pos[n] = {
                "x": round(col_w * (li + 0.5), 1),
                "y": round(gap * (j + 0.5), 1),
                "w": round(nw, 1),
                "h": nh,
                "layer": li,
            }
    return pos


def edge_path(a: dict, b: dict, offset: float = 0.0) -> str:
    ax, ay, bx, by = a["x"], a["y"] + offset, b["x"], b["y"] + offset
    if b["layer"] > a["layer"]:
        sx, ex = ax + a["w"] / 2, bx - b["w"] / 2
        dx = max(40, (ex - sx) / 2)
        return f"M{sx:.1f},{ay:.1f} C{sx+dx:.1f},{ay:.1f} {ex-dx:.1f},{by:.1f} {ex:.1f},{by:.1f}"
    if b["layer"] < a["layer"]:
        sx, ex = ax - a["w"] / 2, bx + b["w"] / 2
        dx = max(40, (sx - ex) / 2)
        return f"M{sx:.1f},{ay:.1f} C{sx-dx:.1f},{ay:.1f} {ex+dx:.1f},{by:.1f} {ex:.1f},{by:.1f}"
    # 같은 계층: 오른쪽으로 돌아감
    sx, ex = ax + a["w"] / 2, bx + b["w"] / 2
    bulge = 70 + abs(by - ay) * 0.15
    return f"M{sx:.1f},{ay:.1f} C{sx+bulge:.1f},{ay:.1f} {ex+bulge:.1f},{by:.1f} {ex:.1f},{by:.1f}"


# ----------------------------------------------------------------------------
# SVG 렌더링
# ----------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def node_svg(n: dict, p: dict, uid: str) -> str:
    kind = n.get("kind", "service")
    color, tag, _ = KINDS.get(kind, KINDS["service"])
    x, y, w, h = p["x"] - p["w"] / 2, p["y"] - p["h"] / 2, p["w"], p["h"]
    label = esc(n.get("label", n["id"]))
    tech = esc(n.get("tech", ""))
    small = h < 70
    fs = 17 if not small else 14
    shape = ""
    if kind in ("db", "storage"):
        ry = 9
        shape = (
            f'<path class="n-body" d="M{x},{y+ry} a{w/2},{ry} 0 0,1 {w},0 v{h-2*ry} a{w/2},{ry} 0 0,1 {-w},0 z"/>'
            f'<path class="n-rim" d="M{x},{y+ry} a{w/2},{ry} 0 0,0 {w},0"/>'
        )
    elif kind == "queue":
        # 파이프 모양: 양 끝에 세로선
        shape = (f'<rect class="n-body" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>'
                 f'<line class="n-rim" x1="{x+9}" y1="{y+10}" x2="{x+9}" y2="{y+h-10}"/>'
                 f'<line class="n-rim" x1="{x+w-9}" y1="{y+10}" x2="{x+w-9}" y2="{y+h-10}"/>')
    elif kind == "ai":
        c = 18
        shape = (f'<path class="n-body" d="M{x+c},{y} H{x+w-c} L{x+w},{y+h/2} L{x+w-c},{y+h} '
                 f'H{x+c} L{x},{y+h/2} Z"/>')
    else:
        rx = 22 if kind == "client" else 12
        dash = ' stroke-dasharray="6 5"' if kind == "external" else ""
        shape = f'<rect class="n-body" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"{dash}/>'
    tag_y = y + (30 if kind in ("db", "storage") else 22)
    tag_svg = "" if small else f'<text class="n-tag" x="{p["x"]}" y="{tag_y}">{tag}</text>'
    ly = p["y"] + (4 if small else 8)
    ty = ly + 20
    tech_svg = f'<text class="n-tech" x="{p["x"]}" y="{ty}">{tech}</text>' if tech and not small else ""
    return (
        f'<g class="node k-{kind}" id="{uid}-n-{esc(n["id"])}" data-id="{esc(n["id"])}" '
        f'style="--c:{color};--d:{p["layer"]*0.12:.2f}s">'
        f'{shape}{tag_svg}<text class="n-label" x="{p["x"]}" y="{ly}" style="font-size:{fs}px">{label}</text>'
        f'{tech_svg}</g>'
    )


def topology_svg(model: dict, uid: str, W: int, H: int, only: list[str] | None = None) -> str:
    nodes = model["nodes"]
    edges = model["edges"]
    if only:
        keep = set(only)
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    pos = layout(nodes, edges, W, H)

    # 같은 노드 쌍 사이 복수 간선은 위아래로 벌린다
    pair_count: dict[tuple, int] = {}
    pair_idx: dict[str, int] = {}
    for e in edges:
        k = tuple(sorted((e["from"], e["to"])))
        pair_idx[e["id"]] = pair_count.get(k, 0)
        pair_count[k] = pair_count.get(k, 0) + 1

    parts = [
        f'<svg class="topo" viewBox="0 0 {W} {H}" data-uid="{uid}" xmlns="http://www.w3.org/2000/svg">',
        "<defs>"
        f'<marker id="{uid}-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="ar"/></marker>'
        f'<marker id="{uid}-arh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="13" markerHeight="13" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="arh"/></marker>'
        f'<filter id="{uid}-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        "</defs>",
        '<g class="edges">',
    ]
    for e in edges:
        a, b = pos[e["from"]], pos[e["to"]]
        k = tuple(sorted((e["from"], e["to"])))
        n = pair_count[k]
        off = (pair_idx[e["id"]] - (n - 1) / 2) * 16 if n > 1 else 0
        d = edge_path(a, b, off)
        asyn = " async" if e.get("async") else ""
        lab = e.get("label") or e.get("protocol") or ""
        parts.append(
            f'<g class="edge{asyn}" id="{uid}-e-{esc(e["id"])}" data-id="{esc(e["id"])}" '
            f'data-from="{esc(e["from"])}" data-to="{esc(e["to"])}" style="--d:{a["layer"]*0.12+0.35:.2f}s">'
            f'<path class="e-geo" d="{d}"/>'
            f'<path class="e-base" d="{d}" pathLength="1" marker-end="url(#{uid}-ar)"/>'
            f'<path class="e-ants" d="{d}"/>'
            f'<path class="e-hl" d="{d}" pathLength="1" marker-end="url(#{uid}-arh)"/>'
            f'<g class="e-lab"><rect rx="6"/><text>{esc(lab)}</text></g>'
            "</g>"
        )
    parts.append("</g><g class=\"nodes\">")
    for n in nodes:
        parts.append(node_svg(n, pos[n["id"]], uid))
    parts.append(f'</g><g class="packets" filter="url(#{uid}-glow)"></g></svg>')
    return "".join(parts)


# ----------------------------------------------------------------------------
# 슬라이드 렌더링
# ----------------------------------------------------------------------------
_COUNT = re.compile(r"^(?P<pre>[^\d]*?)(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suf>.*)$", re.S)


def count_html(value, enabled=True) -> str:
    """'1,600,000 req/s' 같은 값에서 숫자 부분만 카운트업 대상으로 감싼다. 날짜·범위처럼 숫자가 여럿이면 그대로 둔다."""
    text = str(value if value is not None else "")
    m = _COUNT.match(text.strip())
    if not enabled or not m or re.search(r"\d", m["suf"]) or re.search(r"\d", m["pre"]):
        return esc(text)
    num = m["num"]
    dec = len(num.split(".")[1]) if "." in num else 0
    to = float(num.replace(",", ""))
    return (f'{esc(m["pre"])}<span class="num" data-to="{to}" data-dec="{dec}" '
            f'data-comma="{1 if "," in num else 0}">{esc(num)}</span>{esc(m["suf"])}')


def image_src(src: str) -> str:
    """원격 URL·data URI 는 그대로, 로컬 파일은 base64 로 내장해 단일 HTML 을 유지한다."""
    if re.match(r"^(https?:|data:)", src):
        return src
    import base64
    import mimetypes
    f = (BASE_DIR / src)
    mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode("ascii")


def js_src(src: str) -> str:
    """로컬 JS 파일을 data URI 로 내장한다 (scene 의 libs[].src)."""
    import base64
    return "data:text/javascript;base64," + base64.b64encode((BASE_DIR / src).read_bytes()).decode("ascii")


def scene_libs(s: dict) -> list[dict]:
    out = []
    for L in s.get("libs") or []:
        if isinstance(L, str):
            module, url, glob = LIBS[L]
            out.append({"name": L, "url": url, "module": module, "global": glob})
        else:
            url = L["url"] if L.get("url") else js_src(L["src"])
            out.append({"name": L["name"], "url": url, "module": bool(L.get("module")), "global": L.get("global")})
    return out


def scene_js(i: int, s: dict) -> str:
    """scene 슬라이드의 사용자 스크립트를 런타임 레지스트리 항목으로 감싼다. (작성자 코드이므로 이스케이프하지 않는다)"""
    code = s.get("script") or (BASE_DIR / s["script_file"]).read_text(encoding="utf-8-sig")
    code = re.sub(r"</(script)", r"<\\/\1", code, flags=re.I)   # 인라인 <script> 를 조기에 닫지 않게
    libs = json.dumps(scene_libs(s), ensure_ascii=False).replace("</", "<\\/")
    return f"__SCENES[{i}] = {{libs: {libs}, run: async function(ctx){{\n{code}\n}}}};"


def check_assets(deck: dict, base: Path) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    for i, s in enumerate(deck.get("slides", [])):
        if s.get("type") == "scene":
            files = [("script_file", s.get("script_file"))] + [
                ("libs[].src", L.get("src")) for L in s.get("libs") or [] if isinstance(L, dict)]
            for key, f in files:
                if f and not (base / f).is_file():
                    errs.append(f"slides[{i}] (scene): {key} 파일 없음 '{f}' (deck.json 기준 상대 경로)")
        src = s.get("src") if s.get("type") == "image" else None
        if not src or re.match(r"^(https?:|data:)", str(src)):
            continue
        f = base / src
        if not f.is_file():
            errs.append(f"slides[{i}] (image): 파일 없음 '{src}' (deck.json 기준 상대 경로)")
        elif f.stat().st_size > MAX_INLINE_BYTES:
            warns.append(f"slides[{i}] (image): '{src}' {f.stat().st_size // 1024}KB — HTML 이 무거워집니다. 줄여서 쓰세요")
    return errs, warns


def words(h: str) -> str:
    """이미 이스케이프된 인라인 HTML 의 텍스트를 단어 단위 <span class=w> 로 감싼다 (태그는 그대로 통과)."""
    n = 0
    out = []
    for part in re.split(r"(<[^>]+>)", h):
        if part.startswith("<"):
            out.append(part)
            continue
        for tok in re.split(r"(\s+)", part):
            if not tok:
                continue
            if tok.isspace():
                out.append(tok)
            else:
                out.append(f'<span class="w" style="--i:{n}">{tok}</span>')
                n += 1
    return "".join(out)


def bar_style(x: dict) -> str:
    return f' style="--w:{x["bar"]}%"' if "bar" in x else ""


def md_inline(s: str) -> str:
    """**굵게**, `코드` 정도만 지원하는 최소 인라인 마크업."""
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


def slide_html(i: int, s: dict, model: dict, deck: dict) -> tuple[str, int]:
    t = s["type"]
    uid = f"s{i}"
    title = md_inline(s.get("title", ""))
    notes = esc(s.get("notes", ""))
    steps = 0
    body = ""
    cls = f"slide t-{t}"
    data = ""

    if t == "title":
        sysname = model.get("system", {}).get("name", "")
        body = (
            f'<div class="title-wrap"><div class="eyebrow">{esc(deck.get("eyebrow", sysname))}</div>'
            f'<h1 class="words">{words(md_inline(s.get("title") or deck.get("title", "")))}</h1>'
            f'<p class="sub">{md_inline(s.get("subtitle") or deck.get("subtitle", ""))}</p>'
            f'<div class="meta">{esc(deck.get("author", ""))}<span>{esc(deck.get("date", ""))}</span></div></div>'
            f'<div class="title-bg">{topology_svg(model, uid, 1100, 760)}</div>'
        )
        data = ' data-ambient="1"'
    elif t == "section":
        body = (f'<div class="sec"><div class="sec-no">{esc(s.get("no", ""))}</div><h1 class="words">{words(title)}</h1>'
                f'<p class="sub">{md_inline(s.get("subtitle", ""))}</p></div>')
    elif t == "end":
        asks = s.get("asks") or []
        if asks:
            lis = "".join(f'<li class="frag"><span>{md_inline(a)}</span></li>' for a in asks)
            steps = len(asks)
            body = (f'<div class="sec end has-asks"><div class="kicker">{esc(s.get("subtitle") or "요청 사항")}</div>'
                    f'<h1 class="words">{words(title or "함께 정해 주세요")}</h1><ol class="asks">{lis}</ol></div>')
        else:
            body = (f'<div class="sec end"><h1 class="words">{words(title or "감사합니다")}</h1>'
                    f'<p class="sub">{md_inline(s.get("subtitle", "Q & A"))}</p></div>')
    elif t == "statement":
        kick = f'<div class="kicker">{esc(s["kicker"])}</div>' if s.get("kicker") else ""
        sub = f'<p class="sub">{md_inline(s["subtitle"])}</p>' if s.get("subtitle") else ""
        body = f'{kick}<p class="statement words">{words(md_inline(s.get("text", "")))}</p>{sub}'
    elif t == "quote":
        by = f'<div class="by">{md_inline(s["by"])}</div>' if s.get("by") else ""
        body = f'<blockquote class="words">{words(md_inline(s.get("quote", "")))}</blockquote>{by}'
    elif t == "bullets":
        items = s.get("bullets", [])
        reveal = s.get("reveal", True)
        lis = []
        for b in items:
            if isinstance(b, dict):
                sub = "".join(f"<li>{md_inline(x)}</li>" for x in b.get("sub", []))
                lis.append(f'<li class="frag"><span>{md_inline(b.get("text", ""))}</span>'
                           f'{"<ul>" + sub + "</ul>" if sub else ""}</li>')
            else:
                lis.append(f'<li class="frag"><span>{md_inline(b)}</span></li>')
        steps = len(items) if reveal else 0
        body = f'<h2>{title}</h2><ul class="bul{"" if reveal else " all"}">{"".join(lis)}</ul>'
    elif t == "stats":
        items = s.get("items", [])
        cards = "".join(
            f'<div class="stat frag"{bar_style(x)}><div class="v{" long" if len(str(x.get("value", ""))) > 7 else ""}">{count_html(x.get("value"), x.get("count", True))}</div>'
            f'<div class="l">{md_inline(x.get("label", ""))}</div>'
            f'<div class="h">{md_inline(x.get("hint", ""))}</div>'
            f'{"<div class=sbar><i></i></div>" if "bar" in x else ""}</div>' for x in items
        )
        steps = len(items)
        body = f'<h2>{title}</h2><div class="stats n{len(items)}">{cards}</div>'
    elif t == "code":
        magic = s.get("magic") or []
        code = magic[0]["code"] if magic else s.get("code", "")
        hl = set(s.get("highlight", []) or [])
        start = int(s.get("start_line", 1))
        lines = code.rstrip("\n").split("\n")
        rows = "".join(
            f'<span class="ln{" hl" if (start + k) in hl else ""}" data-n="{start + k}" data-t="{esc(l)}">{esc(l) or " "}</span>'
            for k, l in enumerate(lines)
        )
        side = ""
        walk = s.get("walk") or []
        if magic:
            side = '<ul class="code-pts">' + "".join(
                f'<li class="walk">{md_inline(m.get("note", ""))}</li>' for m in magic) + "</ul>"
            steps = len(magic) - 1
            data += (f' data-magic="{esc(json.dumps([{"code": m["code"]} for m in magic], ensure_ascii=False))}"'
                     f' data-start="{start}"')
        elif walk:
            rngs = [list(walk_range(w)) for w in walk]
            side = '<ul class="code-pts">' + "".join(
                f'<li class="walk">{md_inline(w.get("note", ""))}</li>' for w in walk) + "</ul>"
            steps = len(walk)
            data += f' data-walk="{esc(json.dumps(rngs))}"'
        elif s.get("points"):
            side = '<ul class="code-pts">' + "".join(f"<li>{md_inline(p)}</li>" for p in s["points"]) + "</ul>"
        longest = max(len(str(v).rstrip("\n").split("\n")) for v in ([code] + [m["code"] for m in magic]))
        big = " big" if longest <= 12 else ""   # 짧은 코드는 크게 보여 준다
        body = (
            f'<h2>{title}</h2><div class="code-wrap{" with-pts" if side else ""}">'
            f'<div class="code{big}"><div class="file">{esc(s.get("file", ""))}</div>'
            f'<pre><code class="language-{esc(s.get("lang", "plaintext"))}">{rows}</code></pre></div>{side}</div>'
        )
    elif t == "image":
        marks = s.get("marks") or []
        boxes = "".join(
            f'<div class="mark frag{" up" if m["box"][1] + m["box"][3] > 72 else ""}" '
            f'style="left:{m["box"][0]}%;top:{m["box"][1]}%;width:{m["box"][2]}%;height:{m["box"][3]}%">'
            f'{"<span>" + md_inline(m["note"]) + "</span>" if m.get("note") else ""}</div>' for m in marks
        )
        steps = len(marks)
        cap = f'<figcaption>{md_inline(s["caption"])}</figcaption>' if s.get("caption") else ""
        body = (f'<h2>{title}</h2><figure class="shot{" cover" if s.get("fit") == "cover" else ""}"><div class="shot-in">'
                f'<img src="{esc(image_src(s["src"]))}" alt="{esc(s.get("alt", ""))}">{boxes}</div>{cap}</figure>')
    elif t == "terminal":
        items = s.get("items", [])
        rows = []
        worst = "OK"
        for x in items:
            st = str(x.get("status", "OK")).upper()
            worst = max(worst, st, key=["OK", "WARN", "FAIL"].index)
            rows.append(
                f'<div class="trow frag {STATUS[st]}" style="--w:{x.get("progress", 100)}%">'
                f'<span class="tlab">{md_inline(x.get("label", ""))}</span><span class="trk"><i></i></span>'
                f'<span class="tbadge">[{st}]</span><span class="td">{esc(x.get("detail", ""))}</span></div>'
            )
        summ = ""
        if s.get("summary"):
            summ = f'<div class="tsum frag {STATUS[worst]}">{md_inline(s["summary"])}</div>'
        steps = len(items) + (1 if summ else 0)
        cmd = s.get("command", "")
        body = (
            f'<h2>{title}</h2><div class="term"><div class="tbar"><i></i><i></i><i></i>'
            f'<span>{esc(s.get("window_title", "terminal"))}</span></div>'
            f'<div class="tbody"><div class="tcmd"><span class="cmd" data-full="{esc(cmd)}">{esc(cmd)}</span></div>'
            f'{"".join(rows)}{summ}</div></div>'
        )
    elif t == "bento":
        cards = s.get("cards", [])
        html_cards = "".join(
            f'<div class="bcard frag">{"<div class=ic>" + esc(c["icon"]) + "</div>" if c.get("icon") else ""}'
            f'<h3>{md_inline(c.get("title", ""))}</h3><p>{md_inline(c.get("body", ""))}</p></div>' for c in cards
        )
        steps = len(cards)
        body = f'<h2>{title}</h2><div class="bento n{len(cards)}">{html_cards}</div>'
    elif t == "timeline":
        items = s.get("items", [])
        lis = "".join(
            f'<div class="tl-item frag"><div class="per">{esc(x.get("period", ""))}</div>'
            f'<h3>{md_inline(x.get("title", ""))}</h3><p>{md_inline(x.get("detail", ""))}</p></div>' for x in items
        )
        steps = len(items)
        body = f'<h2>{title}</h2><div class="tl">{lis}</div>'
    elif t == "split":
        left ="".join(f"<li>{md_inline(x)}</li>" for x in s.get("left", {}).get("bullets", []))
        right = "".join(f"<li>{md_inline(x)}</li>" for x in s.get("right", {}).get("bullets", []))
        body = (
            f'<h2>{title}</h2><div class="split">'
            f'<div class="col"><h3>{md_inline(s.get("left", {}).get("title", ""))}</h3><ul>{left}</ul></div>'
            f'<div class="col"><h3>{md_inline(s.get("right", {}).get("title", ""))}</h3><ul>{right}</ul></div></div>'
        )
    elif t == "topology":
        only = s.get("nodes")
        svg = topology_svg(model, uid, 1480, 690, only)
        focus = s.get("focus") or []
        cap = f'<p class="cap">{md_inline(s.get("caption", ""))}</p>' if s.get("caption") else ""
        body = f'<h2>{title}</h2><div class="topo-wrap">{svg}</div>{cap}'
        flow = s.get("flow")
        if flow:
            f = next(x for x in model["flows"] if x["id"] == flow)
            data += f' data-autoflow="{esc(json.dumps([[st["edge"], bool(st.get("reverse"))] for st in f["steps"]]))}"'
        if focus:
            data += f' data-focus="{esc(json.dumps(focus))}"'
        data += ' data-ambient="1"'
        legend = legend_html(model, only)
        body += legend
    elif t == "flow":
        f = next(x for x in model["flows"] if x["id"] == s["flow"])
        only = s.get("nodes")
        svg = topology_svg(model, uid, 940, 700, only)
        names = {n["id"]: n.get("label", n["id"]) for n in model["nodes"]}
        emap = {e["id"]: e for e in model["edges"]}
        lis = []
        for k, st in enumerate(f["steps"]):
            e = emap[st["edge"]]
            a, b = (e["to"], e["from"]) if st.get("reverse") else (e["from"], e["to"])
            lis.append(
                f'<li><span class="no">{k+1}</span><div><div class="hop">{esc(names[a])} '
                f'<i>→</i> {esc(names[b])}</div><div class="note">{md_inline(st.get("note", e.get("label", "")))}</div></div></li>'
            )
        steps = len(f["steps"])
        data += f' data-flow="{esc(json.dumps([[st["edge"], bool(st.get("reverse"))] for st in f["steps"]]))}"'
        body = (
            f'<h2>{title or md_inline(f.get("title", ""))}</h2>'
            f'<div class="flow-grid"><div class="topo-wrap">{svg}</div>'
            f'<aside class="steps"><p class="fdesc">{md_inline(s.get("description") or f.get("description", ""))}</p>'
            f'<ol>{"".join(lis)}</ol></aside></div>'
        )
    elif t == "scene":
        # html/css 는 작성자가 쓴 마크업이라 그대로 넣는다. css 의 :scope 는 이 장면 영역으로 바뀐다
        host = f"{uid}-scene"
        css = str(s.get("css", "")).replace(":scope", f"#{host}").replace("</", "<\\/")
        full = bool(s.get("full"))
        cls += " full" if full else ""
        head = f"<h2>{title}</h2>" if title else ""
        cap = f'<p class="cap">{md_inline(s["caption"])}</p>' if s.get("caption") else ""
        fb = md_inline(s.get("fallback") or "이 장면을 불러오지 못했습니다")
        body = (f'{head}<div class="scene-wrap"><div class="scene" id="{host}">{s.get("html", "")}</div>'
                f'<div class="scene-fb">{fb}</div></div>{cap}{"<style>" + css + "</style>" if css else ""}')
        steps = s.get("steps", 0)
        data += f' data-scene="{i}"'
    tr = s.get("transition") or deck.get("transition", "slide-left")
    if s.get("fx"):
        data += f' data-fx="{esc(s["fx"])}"'
    return (
        f'<section class="{cls}" data-steps="{steps}" data-tr="{esc(tr)}"{data}>{body}'
        f'<aside class="notes">{notes}</aside><div class="pg">{i+1}</div></section>',
        steps,
    )


def legend_html(model: dict, only=None) -> str:
    kinds = []
    for n in model["nodes"]:
        if only and n["id"] not in only:
            continue
        k = n.get("kind", "service")
        if k not in kinds:
            kinds.append(k)
    items = "".join(f'<span><i style="background:{KINDS[k][0]}"></i>{KINDS[k][1]}</span>' for k in kinds)
    has_async = any(e.get("async") for e in model["edges"])
    if has_async:
        items += '<span><i class="dash"></i>비동기</span>'
    return f'<div class="legend">{items}</div>'


# ----------------------------------------------------------------------------
# 페이지 조립
# ----------------------------------------------------------------------------
def build(deck_path: Path, out: Path | None, validate_only: bool, strict: bool = False) -> int:
    deck = json.loads(deck_path.read_text(encoding="utf-8-sig"))   # 메모장 등이 붙이는 BOM 허용
    model_ref = deck.get("model")
    if isinstance(model_ref, str):
        model = json.loads((deck_path.parent / model_ref).read_text(encoding="utf-8-sig"))
    elif isinstance(model_ref, dict):
        model = model_ref
    else:
        raise DeckError("deck.json 에 model(경로 또는 객체)이 필요합니다")
    model.setdefault("flows", [])

    global BASE_DIR
    BASE_DIR = deck_path.parent
    errs = validate(model, deck)
    asset_errs, asset_warns = check_assets(deck, BASE_DIR)
    errs += asset_errs
    if errs:
        print("검증 실패:", file=sys.stderr)
        for e in errs:
            print("  -", e, file=sys.stderr)
        return 1
    warns = lint(deck) + asset_warns
    if warns:
        print(f"경고 {len(warns)}건:", file=sys.stderr)
        for w in warns:
            print("  -", w, file=sys.stderr)
        if strict:
            return 1
    if validate_only:
        print(f"OK: 노드 {len(model['nodes'])}, 간선 {len(model['edges'])}, 플로우 {len(model['flows'])}, "
              f"슬라이드 {len(deck.get('slides', []))}")
        return 0

    slides = [slide_html(i, s, model, deck)[0] for i, s in enumerate(deck["slides"])]
    scenes = [scene_js(i, s) for i, s in enumerate(deck["slides"]) if s["type"] == "scene"]
    scene_block = ""
    if scenes:
        # 장면 스크립트가 ctx.model 로 시스템 모델(노드·간선·흐름)을 읽을 수 있게 함께 싣는다
        mjson = json.dumps({k: model.get(k) for k in ("system", "nodes", "edges", "flows")}, ensure_ascii=False)
        kinds = json.dumps({k: v[0] for k, v in KINDS.items()})
        scene_block = ("<script>\nconst __SCENES = window.__SCENES = {};\nwindow.__MODEL = "
                       + mjson.replace("</", "<\\/") + ";\nwindow.__KINDS = " + kinds + ";\n"
                       + "\n".join(scenes) + "\n</script>")
    theme = deck.get("theme", "aurora")
    if theme not in THEMES:
        raise DeckError(f"theme 은 {' | '.join(THEMES)} 중 하나여야 합니다 (현재: {theme})")
    accent = deck.get("accent") or ACCENTS[theme]
    tpl = (Path(__file__).parent / "deck_template.html").read_text(encoding="utf-8")
    page = (
        tpl.replace("{{TITLE}}", esc(deck.get("title", model.get("system", {}).get("name", "Deck"))))
        .replace("{{THEME}}", esc(theme))
        .replace("{{ACCENT}}", esc(accent))
        .replace("{{SLIDES}}", "\n".join(slides))
        .replace("{{SCENES}}", scene_block)
    )
    out = out or deck_path.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"생성 완료: {out}  (슬라이드 {len(slides)}장)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="시스템 모델로 애니메이션 토폴로지가 들어간 HTML 장표 생성")
    ap.add_argument("deck", type=Path, help="deck.json 경로")
    ap.add_argument("-o", "--out", type=Path, help="출력 HTML 경로 (기본: deck.json 옆)")
    ap.add_argument("--validate-only", action="store_true", help="검증만 수행")
    ap.add_argument("--strict", action="store_true", help="린트 경고(길이·근거 누락 등)가 있으면 실패 처리")
    a = ap.parse_args()
    try:
        sys.exit(build(a.deck, a.out, a.validate_only, a.strict))
    except DeckError as e:
        print("오류:", e, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
