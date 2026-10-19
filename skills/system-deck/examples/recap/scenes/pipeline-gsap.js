// GSAP + SVG: 녹음 → 업로드 → 전사 → 요약 → 저장을 곡선 위 정거장으로 그리고, → 키마다 패킷이 다음 정거장으로 이동한다.
// 라벨은 시스템 모델(ctx.model)에서 읽는다. 색은 CSS 변수를 그대로 써서 테마 전환을 따라간다.
const gsap = ctx.lib.gsap;
const NS = 'http://www.w3.org/2000/svg';
const make = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};

const ids = ['web', 'minio', 'stt', 'claude', 'pg'];
const nodes = ids.map(id => ctx.model.nodes.find(n => n.id === id));
const W = ctx.width, H = ctx.height;
const pts = nodes.map((_, i) => ({ x: 120 + i * (W - 240) / (nodes.length - 1), y: H / 2 + (i % 2 ? -110 : 90) }));

const svg = make('svg', { viewBox: `0 0 ${W} ${H}` }, ctx.el);
const defs = make('defs', {}, svg);
const glow = make('filter', { id: 'pipe-glow', x: '-100%', y: '-100%', width: '300%', height: '300%' }, defs);
make('feGaussianBlur', { stdDeviation: 8 }, glow);
make('feMerge', {}, glow).append(make('feMergeNode', {}), make('feMergeNode', { in: 'SourceGraphic' }));

let d = `M${pts[0].x},${pts[0].y}`;
for (let i = 1; i < pts.length; i++) {
  const a = pts[i - 1], b = pts[i], mx = (a.x + b.x) / 2;
  d += ` C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`;
}
const base = make('path', { d, fill: 'none', 'stroke-width': 3, 'stroke-dasharray': '2 10', 'stroke-linecap': 'round', style: 'stroke:var(--edge)' }, svg);
const done = make('path', { d, fill: 'none', 'stroke-width': 5, 'stroke-linecap': 'round', pathLength: 1, 'stroke-dasharray': 1, 'stroke-dashoffset': 1, style: 'stroke:var(--accent)' }, svg);

// 각 정거장이 경로 위 몇 % 지점인지 표본으로 찾는다
const L = base.getTotalLength();
const frac = pts.map(p => {
  let best = 0, bd = Infinity;
  for (let s = 0; s <= 400; s++) {
    const q = base.getPointAtLength(L * s / 400), dd = (q.x - p.x) ** 2 + (q.y - p.y) ** 2;
    if (dd < bd) { bd = dd; best = s / 400; }
  }
  return best;
});

// 초기 좌표를 꼭 준다: 슬라이드를 떠날 때 GSAP 이 애니메이션 전 값으로 되돌린다
const ring = make('circle', { cx: pts[0].x, cy: pts[0].y, r: 40, fill: 'none', 'stroke-width': 2, style: 'stroke:var(--accent)' }, svg);
const stations = nodes.map((n, i) => {
  const g = make('g', { class: 'st' }, svg);
  const c = ctx.kindColor(n.kind);
  make('circle', { cx: pts[i].x, cy: pts[i].y, r: 34, 'stroke-width': 2.5, style: `fill:var(--bg);stroke:${c}` }, g);
  make('text', { x: pts[i].x, y: pts[i].y + 7, 'text-anchor': 'middle', 'font-size': 20, 'font-weight': 800, style: `fill:${c}` }, g).textContent = i + 1;
  const up = i % 2 === 1, ly = pts[i].y + (up ? -92 : 76);   // 위쪽 정거장은 라벨 두 줄을 원 위로 올린다
  make('text', { x: pts[i].x, y: ly, 'text-anchor': 'middle', 'font-size': 26, 'font-weight': 700, style: 'fill:var(--fg)' }, g).textContent = n.label;
  make('text', { x: pts[i].x, y: ly + 30, 'text-anchor': 'middle', 'font-size': 17, style: 'fill:var(--muted)' }, g).textContent = n.tech || '';
  return g;
});
const packet = make('circle', { r: 11, filter: 'url(#pipe-glow)', style: 'fill:var(--accent)' }, svg);

const st = { p: 0 };
function draw() {
  const q = base.getPointAtLength(L * st.p);
  packet.setAttribute('cx', q.x); packet.setAttribute('cy', q.y);
  done.setAttribute('stroke-dashoffset', 1 - st.p);
}

return {
  enter() {
    st.p = 0; draw();
    gsap.from(stations, { y: 36, duration: 0.8, stagger: 0.09, ease: 'back.out(1.8)' });   // 투명도는 step 이 맡는다
    gsap.fromTo(ring, { attr: { r: 36 }, opacity: 0.9 }, { attr: { r: 64 }, opacity: 0, duration: 1.4, repeat: -1, ease: 'power1.out' });
  },
  step(k, still) {
    gsap.to(st, { p: frac[k], duration: still ? 0 : 1.1, ease: 'power2.inOut', onUpdate: draw, overwrite: true });
    gsap.set(ring, { attr: { cx: pts[k].x, cy: pts[k].y } });
    stations.forEach((g, i) => gsap.to(g, { opacity: i <= k ? 1 : 0.35, duration: still ? 0 : 0.4 }));
  },
};
