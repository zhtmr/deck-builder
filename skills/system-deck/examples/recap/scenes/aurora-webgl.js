// WebGL(라이브러리 없음): 포인트 색으로 흐르는 오로라를 프래그먼트 셰이더로 그린다.
const c = ctx.canvas();
const gl = c.getContext('webgl', { preserveDrawingBuffer: true });   // 오버뷰·PDF 에도 마지막 프레임이 남게
if (!gl) throw new Error('WebGL 을 쓸 수 없는 환경입니다');

const VS = 'attribute vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }';
const FS = `precision mediump float;
uniform vec2 res; uniform float t; uniform vec3 acc; uniform vec3 bg;
void main(){
  vec2 uv = gl_FragCoord.xy / res;
  vec2 p = uv * vec2(res.x / res.y, 1.0) * 1.6;
  float v = 0.0;
  for (int i = 0; i < 5; i++){
    float f = float(i);
    p += vec2(sin(p.y * 1.3 + t * 0.22 + f), cos(p.x * 1.1 - t * 0.18 + f * 1.7)) * 0.32;
    v += sin(p.x * 1.6 + p.y * 1.2 + f * 0.8);
  }
  v = 0.5 + 0.5 * sin(v * 0.9);
  float band = smoothstep(0.35, 0.95, v) * smoothstep(0.0, 0.7, uv.y);
  vec3 col = mix(bg, acc, band * 0.75) + acc * pow(band, 6.0) * 0.35;
  float vig = smoothstep(1.25, 0.25, length(uv - vec2(0.55, 0.5)));
  gl_FragColor = vec4(mix(bg, col, vig), 1.0);
}`;

function shader(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
gl.linkProgram(prog);
gl.useProgram(prog);

gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);   // 화면을 덮는 삼각형 하나
const loc = gl.getAttribLocation(prog, 'p');
gl.enableVertexAttribArray(loc);
gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
const U = n => gl.getUniformLocation(prog, n);

// CSS 색 문자열(#hex, rgb() 등)을 0~1 RGB 로
const probe = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
function rgb(css) {
  probe.fillStyle = '#000'; probe.fillStyle = css; probe.fillRect(0, 0, 1, 1);
  const d = probe.getImageData(0, 0, 1, 1).data;
  return [d[0] / 255, d[1] / 255, d[2] / 255];
}
function colors(th) {
  gl.uniform3fv(U('acc'), rgb(th.accent));
  gl.uniform3fv(U('bg'), rgb(th.bg));
}
colors(ctx.theme());

ctx.loop(t => {
  gl.viewport(0, 0, c.width, c.height);
  gl.uniform2f(U('res'), c.width, c.height);
  gl.uniform1f(U('t'), t + 8);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
});

return { theme: colors };
