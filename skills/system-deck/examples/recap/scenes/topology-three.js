// Three.js + GSAP: 시스템 모델의 노드·간선을 3D 로 띄워 천천히 돈다.
// → 키를 누르면 카메라가 다가가고(GSAP), 대표 흐름의 패킷이 간선을 따라 순서대로 이동한다.
const THREE = ctx.lib.three, gsap = ctx.lib.gsap;
const { nodes, edges, flows } = ctx.model;

const renderer = new THREE.WebGLRenderer({ canvas: ctx.canvas(), antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(ctx.pixelRatio());
renderer.setSize(ctx.width, ctx.height, false);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(24, ctx.width / ctx.height, 0.1, 100);   // 좁은 화각: 가까운 노드가 과하게 커지지 않게
scene.add(new THREE.AmbientLight(0xffffff, 1.2));
const sun = new THREE.PointLight(0xffffff, 60);
sun.position.set(4, 6, 6);
scene.add(sun);

// 계층: 역방향 간선을 뺀 그래프의 최장 경로 (build_deck.py 의 2D 레이아웃과 같은 생각)
const out = Object.fromEntries(nodes.map(n => [n.id, []]));
edges.forEach(e => out[e.from].push(e.to));
const state = {}, fwd = [];
const dfs = u => {
  state[u] = 1;
  for (const v of out[u]) { if (state[v] === 1) continue; fwd.push([u, v]); if (!state[v]) dfs(v); }
  state[u] = 2;
};
nodes.filter(n => n.kind === 'client').concat(nodes).forEach(n => state[n.id] || dfs(n.id));
const layer = Object.fromEntries(nodes.map(n => [n.id, 0]));
for (let i = 0; i < nodes.length; i++) fwd.forEach(([u, v]) => { layer[v] = Math.max(layer[v], layer[u] + 1); });
const L = Math.max(...Object.values(layer)) + 1;

// 같은 계층의 노드는 x 축을 중심으로 한 원 위에 둔다
const pos = {};
for (let l = 0; l < L; l++) {
  const ids = nodes.filter(n => layer[n.id] === l).map(n => n.id);
  ids.forEach((id, j) => {
    const a = (j / ids.length) * Math.PI * 2 + l * 0.9, r = ids.length > 1 ? 1.7 : 0;
    pos[id] = new THREE.Vector3((l - (L - 1) / 2) * 2.4, Math.sin(a) * r, Math.cos(a) * r);
  });
}
// 카메라가 원점을 보며 돌므로 노드 묶음의 중심을 원점에 맞춘다
const center = new THREE.Box3().setFromPoints(Object.values(pos)).getCenter(new THREE.Vector3());
Object.values(pos).forEach(p => p.sub(center));

// 빛 번짐 스프라이트용 원형 그라데이션
const glowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.35, 'rgba(255,255,255,.35)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();
const glow = (color, size) => {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  s.scale.setScalar(size);
  return s;
};

function textSprite(text, color) {
  const fs = 48, c = document.createElement('canvas'), g = c.getContext('2d');
  const font = `700 ${fs}px Pretendard, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif`;
  g.font = font;
  c.width = Math.ceil(g.measureText(text).width) + 24; c.height = fs + 20;
  g.font = font; g.fillStyle = color; g.textBaseline = 'middle'; g.fillText(text, 12, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set((c.width / c.height) * 0.3, 0.3, 1);
  return s;
}

const labels = [];
nodes.forEach(n => {
  const col = new THREE.Color(ctx.kindColor(n.kind));
  const m = new THREE.Mesh(new THREE.SphereGeometry(0.26, 32, 16),
    new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.45, roughness: 0.35 }));
  m.position.copy(pos[n.id]);
  m.add(glow(col, 1.5));
  scene.add(m);
  const lab = textSprite(n.label, ctx.theme().fg);
  lab.position.copy(pos[n.id]).add(new THREE.Vector3(0, -0.52, 0));
  labels.push([lab, n.label]);
  scene.add(lab);
});

// 간선: 위로 살짝 휜 곡선. 비동기 간선은 점선
const edgeObj = {};
edges.forEach(e => {
  const a = pos[e.from], b = pos[e.to];
  const mid = a.clone().add(b).multiplyScalar(0.5).add(new THREE.Vector3(0, 0.55, 0));
  const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
  const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48));
  const mat = e.async
    ? new THREE.LineDashedMaterial({ color: ctx.theme().muted, dashSize: 0.12, gapSize: 0.1, transparent: true, opacity: 0.6 })
    : new THREE.LineBasicMaterial({ color: ctx.theme().muted, transparent: true, opacity: 0.6 });
  const line = new THREE.Line(geo, mat);
  if (e.async) line.computeLineDistances();
  scene.add(line);
  edgeObj[e.id] = { curve, mat };
});

const flow = flows[0];
const accent = new THREE.Color(ctx.theme().accent);
const packet = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 8), new THREE.MeshBasicMaterial({ color: accent }));
packet.add(glow(accent, 0.9));
packet.visible = false;
scene.add(packet);

const view = { r: 24, y: 4.5 };   // GSAP 이 → 키에 맞춰 이 값을 보간한다
const muted = new THREE.Color(ctx.theme().muted);
let playing = false;

ctx.loop(t => {
  const a = t * 0.12 + 0.6;
  camera.position.set(Math.sin(a) * view.r, view.y, Math.cos(a) * view.r);
  camera.lookAt(0, 0, 0);
  Object.values(edgeObj).forEach(o => o.mat.color.copy(muted));
  if (playing && flow) {
    const per = 0.9, k = Math.floor(t / per) % flow.steps.length, u = (t % per) / per;
    const s = flow.steps[k], o = edgeObj[s.edge];
    o.mat.color.copy(accent);
    packet.position.copy(o.curve.getPoint(s.reverse ? 1 - u : u));
  }
  packet.visible = playing && !!flow;
  renderer.render(scene, camera);
});

return {
  enter() { view.r = 24; view.y = 4.5; },   // GSAP 이 바꾸는 값은 처음 값을 직접 정한다(결정성 규약)
  step(k, still) {
    playing = k >= 1;
    gsap.to(view, { r: playing ? 19 : 24, y: playing ? 3 : 4.5, duration: still ? 0 : 1.4, ease: 'power3.inOut', overwrite: true });
  },
  resize(w, h, pr) {
    renderer.setPixelRatio(pr);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  },
  theme(th) {
    accent.set(th.accent);
    muted.set(th.muted);
    packet.material.color.copy(accent);
    packet.children[0].material.color.copy(accent);
    labels.forEach(([s, text]) => {   // 글자색이 바뀌므로 라벨 텍스처를 다시 만든다
      const n = textSprite(text, th.fg);
      s.material.map.dispose();
      s.material.map = n.material.map;
      s.scale.copy(n.scale);
    });
  },
};
