// Canvas 2D: 흩어져 흐르던 점들이 → 키를 누르면 오른쪽의 문서(회의록) 줄 모양으로 모인다.
// ctx.canvas2d() 는 고해상도 스케일이 적용된 2D 컨텍스트를 준다(좌표는 무대 px).
const g = ctx.canvas2d();
const N = ctx.reduced ? 500 : 1100;
let W = ctx.width, H = ctx.height, mode = 0, color = ctx.theme().accent;

const P = Array.from({ length: N }, () => ({
  x: Math.random() * W, y: Math.random() * H, tx: 0, ty: 0,
  r: 0.8 + Math.random() * 1.8, a: 0.25 + Math.random() * 0.6,
}));

// 회의록 모양: 오른쪽에 제목 줄 + 본문 줄 8개
function targets() {
  const x0 = W * 0.6, w = W * 0.32, y0 = H * 0.2, rows = 9, gap = (H * 0.6) / (rows - 1);
  P.forEach((p, i) => {
    const r = i % rows, len = r === 0 ? 0.5 : r % 4 === 3 ? 0.62 : 1;
    p.tx = x0 + Math.random() * w * len;
    p.ty = y0 + r * gap + (Math.random() - 0.5) * (r === 0 ? 12 : 5);
  });
}
targets();

function draw() {
  g.clearRect(0, 0, W, H);
  g.fillStyle = color;
  for (const p of P) {
    g.globalAlpha = mode ? Math.min(1, p.a + 0.3) : p.a;
    g.beginPath(); g.arc(p.x, p.y, p.r, 0, Math.PI * 2); g.fill();
  }
  g.globalAlpha = 1;
}

ctx.loop((t, dt) => {
  for (const p of P) {
    if (mode) {
      const k = Math.min(1, dt * 2.6);
      p.x += (p.tx - p.x) * k; p.y += (p.ty - p.y) * k;
    } else {
      // 느린 흐름장: 위치와 시간으로 정한 방향으로 떠다니다 화면 밖으로 나가면 반대편에서 들어온다
      const ang = Math.sin(p.y * 0.004 + t * 0.35) * 1.6 + Math.cos(p.x * 0.003 - t * 0.25);
      p.x += Math.cos(ang) * 38 * dt; p.y += Math.sin(ang) * 38 * dt;
      if (p.x < -5) p.x = W + 5; if (p.x > W + 5) p.x = -5;
      if (p.y < -5) p.y = H + 5; if (p.y > H + 5) p.y = -5;
    }
  }
  draw();
});

return {
  step(k, still) {
    mode = k;
    if (still && mode) P.forEach(p => { p.x = p.tx; p.y = p.ty; });   // 정지 화면은 다 모인 상태
  },
  resize(w, h) { W = w; H = h; targets(); },
  theme(th) { color = th.accent; draw(); },
};
