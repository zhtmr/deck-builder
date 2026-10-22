// Canvas 2D: 흩어져 흐르던 점들이 → 키를 누르면 오른쪽의 문서(회의록) 줄 모양으로 모인다.
// ctx.canvas2d() 는 고해상도 스케일이 적용된 2D 컨텍스트를 준다(좌표는 무대 px).
// 결정성 규약: 점의 위치를 프레임마다 누적하지 않고 시각(t)과 스텝 정보({k, ts, from})로 바로 계산한다.
// 무작위 값은 ctx.rand(i, salt) 로 얻어 다시 열어도, 시각을 지정해 찍어도 같은 화면이 나온다.
const g = ctx.canvas2d();
const N = ctx.reduced ? 500 : 1100;
let W = ctx.width, H = ctx.height, color = ctx.theme().accent;
const { rand } = ctx;

const P = Array.from({ length: N }, (_, i) => ({
  u: rand(i, 1), v: rand(i, 2), sp: 0.6 + rand(i, 3) * 0.8, ph: rand(i, 4) * Math.PI * 2,
  r: 0.8 + rand(i, 5) * 1.8, a: 0.25 + rand(i, 6) * 0.6, tx: 0, ty: 0,
}));

// 회의록 모양: 오른쪽에 제목 줄 + 본문 줄 8개
function targets() {
  const x0 = W * 0.6, w = W * 0.32, y0 = H * 0.2, rows = 9, gap = (H * 0.6) / (rows - 1);
  P.forEach((p, i) => {
    const r = i % rows, len = r === 0 ? 0.5 : r % 4 === 3 ? 0.62 : 1;
    p.tx = x0 + rand(i, 7) * w * len;
    p.ty = y0 + r * gap + (rand(i, 8) - 0.5) * (r === 0 ? 12 : 5);
  });
}
targets();

// 흐름: 출발점에서 점마다 정한 방향으로 떠가며 출렁인다. 화면 밖으로 나가면 반대편에서 들어온다
const wrap = (x, m) => ((x % m) + m) % m;
function flow(p, t) {
  const x = p.u * W + Math.cos(p.ph) * 38 * p.sp * t + Math.sin(t * 0.35 + p.ph) * 24;
  const y = p.v * H + Math.sin(p.ph) * 38 * p.sp * t + Math.cos(t * 0.25 + p.ph * 1.3) * 24;
  return [wrap(x + 5, W + 10) - 5, wrap(y + 5, H + 10) - 5];
}
const ease = u => 1 - Math.pow(1 - Math.min(1, u), 3);

ctx.loop((t, dt, { k, ts, from }) => {
  // 문서 쪽으로 모인 정도 0~1. 스텝이 바뀌면 1.2초 동안 그 방향으로 옮겨 간다
  const e = ease(ts / 1.2), m = k === from ? (k ? 1 : 0) : k ? e : 1 - e;
  g.clearRect(0, 0, W, H);
  g.fillStyle = color;
  for (const p of P) {
    const [fx, fy] = flow(p, t);
    g.globalAlpha = Math.min(1, p.a + 0.3 * m);
    g.beginPath(); g.arc(fx + (p.tx - fx) * m, fy + (p.ty - fy) * m, p.r, 0, Math.PI * 2); g.fill();
  }
  g.globalAlpha = 1;
});

return {
  resize(w, h) { W = w; H = h; targets(); },
  theme(th) { color = th.accent; },
};
