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

SLIDE_TYPES = {"title", "section", "bullets", "topology", "flow", "code", "stats", "split", "end"}


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
    return errs


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
def md_inline(s: str) -> str:
    """**굵게**, `코드` 정도만 지원하는 최소 인라인 마크업."""
    out = esc(s)
    import re
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
            f'<h1>{md_inline(s.get("title") or deck.get("title", ""))}</h1>'
            f'<p class="sub">{md_inline(s.get("subtitle") or deck.get("subtitle", ""))}</p>'
            f'<div class="meta">{esc(deck.get("author", ""))}<span>{esc(deck.get("date", ""))}</span></div></div>'
            f'<div class="title-bg">{topology_svg(model, uid, 1100, 760)}</div>'
        )
        data = ' data-ambient="1"'
    elif t == "section":
        body = (f'<div class="sec"><div class="sec-no">{esc(s.get("no", ""))}</div><h1>{title}</h1>'
                f'<p class="sub">{md_inline(s.get("subtitle", ""))}</p></div>')
    elif t == "end":
        body = (f'<div class="sec end"><h1>{title or "감사합니다"}</h1>'
                f'<p class="sub">{md_inline(s.get("subtitle", "Q & A"))}</p></div>')
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
            f'<div class="stat frag"><div class="v">{esc(x.get("value"))}</div>'
            f'<div class="l">{md_inline(x.get("label", ""))}</div>'
            f'<div class="h">{md_inline(x.get("hint", ""))}</div></div>' for x in items
        )
        steps = len(items)
        body = f'<h2>{title}</h2><div class="stats n{len(items)}">{cards}</div>'
    elif t == "code":
        code = s.get("code", "")
        hl = set(s.get("highlight", []) or [])
        start = int(s.get("start_line", 1))
        lines = code.rstrip("\n").split("\n")
        rows = "".join(
            f'<span class="ln{" hl" if (start + k) in hl else ""}" data-n="{start + k}">{esc(l) or " "}</span>'
            for k, l in enumerate(lines)
        )
        side = ""
        if s.get("points"):
            side = '<ul class="code-pts">' + "".join(f"<li>{md_inline(p)}</li>" for p in s["points"]) + "</ul>"
        body = (
            f'<h2>{title}</h2><div class="code-wrap{" with-pts" if side else ""}">'
            f'<div class="code"><div class="file">{esc(s.get("file", ""))}</div>'
            f'<pre><code class="language-{esc(s.get("lang", "plaintext"))}">{rows}</code></pre></div>{side}</div>'
        )
    elif t == "split":
        left = "".join(f"<li>{md_inline(x)}</li>" for x in s.get("left", {}).get("bullets", []))
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
    return (
        f'<section class="{cls}" data-steps="{steps}"{data}>{body}'
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
def build(deck_path: Path, out: Path | None, validate_only: bool) -> int:
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    model_ref = deck.get("model")
    if isinstance(model_ref, str):
        model = json.loads((deck_path.parent / model_ref).read_text(encoding="utf-8"))
    elif isinstance(model_ref, dict):
        model = model_ref
    else:
        raise DeckError("deck.json 에 model(경로 또는 객체)이 필요합니다")
    model.setdefault("flows", [])

    errs = validate(model, deck)
    if errs:
        print("검증 실패:", file=sys.stderr)
        for e in errs:
            print("  -", e, file=sys.stderr)
        return 1
    if validate_only:
        print(f"OK: 노드 {len(model['nodes'])}, 간선 {len(model['edges'])}, 플로우 {len(model['flows'])}, "
              f"슬라이드 {len(deck.get('slides', []))}")
        return 0

    slides = [slide_html(i, s, model, deck)[0] for i, s in enumerate(deck["slides"])]
    theme = deck.get("theme", "dark")
    if theme not in ("dark", "light", "toss"):
        raise DeckError(f"theme 은 dark | light | toss 중 하나여야 합니다 (현재: {theme})")
    accent = deck.get("accent") or {"toss": "#3182f6", "light": "#2563eb"}.get(theme, "#7dd3fc")
    tpl = (Path(__file__).parent / "deck_template.html").read_text(encoding="utf-8")
    page = (
        tpl.replace("{{TITLE}}", esc(deck.get("title", model.get("system", {}).get("name", "Deck"))))
        .replace("{{THEME}}", esc(theme))
        .replace("{{ACCENT}}", esc(accent))
        .replace("{{SLIDES}}", "\n".join(slides))
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
    a = ap.parse_args()
    try:
        sys.exit(build(a.deck, a.out, a.validate_only))
    except DeckError as e:
        print("오류:", e, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
