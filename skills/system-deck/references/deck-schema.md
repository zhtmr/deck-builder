# deck.json 명세

```jsonc
{
  "title": "장표 제목", "subtitle": "부제", "eyebrow": "제목 위 작은 문구",
  "author": "이름 · 역할", "date": "2026.10",
  "theme": "aurora",          // aurora(기본) | dark | light | toss
  "accent": "#8ab4ff",        // 선택. 생략하면 테마 기본값 (aurora #8ab4ff, dark #7dd3fc, light #2563eb, toss #3182f6)
  "transition": "slide-left", // 선택. 덱 전체 기본 전환 (아래 "모션")
  "model": "system-model.json",  // deck.json 기준 상대 경로 (또는 모델 객체를 그대로)
  "slides": [ ... ]
}
```

모든 슬라이드 공통: `type`, `title`, `notes`(발표자 노트).
`title` 은 주장형 한 문장(`storytelling.md` 3절). `title`·`section`·`statement`·`quote`·`end` 를 뺀 타입에서 "전체 구성", "결과" 같은 주제형이나 한 단어 제목이면 린트가 경고한다.
텍스트 필드는 `**굵게**`(포인트 색), `` `코드` `` 만 지원한다.

| type | 필드 | 스텝(→ 키) | 쓰임 |
|---|---|---|---|
| `title` | (덱의 title/subtitle/author 사용) | 없음 | 첫 장. 배경에 전체 토폴로지 |
| `section` | `no`, `title`, `subtitle` | 없음 | 장 구분 |
| `bullets` | `bullets`: 문자열 또는 `{text, sub:[...]}` · `reveal`(기본 true) | 항목 수 | 3~5개 권장, 항목당 1줄 |
| `topology` | `flow`(자동 순환할 흐름 id) · `focus`(강조할 노드 id 목록) · `nodes`(보여 줄 노드 부분집합) · `caption` | 없음 | 구성도. flow 를 주면 패킷이 단계별로 계속 순환 |
| `flow` | `flow`(필수) · `nodes` · `description` | 단계 수 | 왼쪽 토폴로지 + 오른쪽 단계 목록, 한 단계씩 진행 |
| `code` | `file`, `lang`, `start_line`, 그리고 아래 셋 중 하나: ① `code` + `highlight`(라인 번호 목록) + `points`(설명 3개 이하) ② `code` + `walk` ③ `magic` | ②③ 단계 수 | 20줄 이하 발췌 |
| `split` | `left:{title, bullets}`, `right:{title, bullets}` | 없음 | 비교, 전/후 |
| `stats` | `items:[{value, label, hint, bar, source, count}]` (1~6개). `bar` 0~100 이면 비교 막대. `count:false` 면 카운트업 끔 | 항목 수 | 결과 지표 (숫자가 목표값까지 올라간다) |
| `terminal` | `window_title`, `command`, `items:[{label, status(OK/WARN/FAIL), progress(0~100), detail, source}]`(1~7개), `summary` | 항목 수(+요약) | 점검·검증·마이그레이션 현황 |
| `bento` | `cards:[{icon, title, body}]` (2~4개) | 카드 수 | 핵심 효과·특징 요약 |
| `timeline` | `items:[{period, title, detail}]` (2~6개) | 항목 수 | 구현 과정, 로드맵 |
| `image` | `src`(필수), `alt`, `caption`, `fit`(`contain`/`cover`), `marks:[{box:[x,y,w,h], note}]` | `marks` 수 | 제품 화면·대시보드·다이어그램 캡처. `box` 는 이미지 대비 % (x+w, y+h ≤ 100). → 키마다 한 영역을 강조하고 나머지는 어두워진다 |
| `statement` | `text`, `kicker`, `subtitle` | 없음 | 핵심 메시지 한 문장 (단어 단위로 등장) |
| `quote` | `quote`, `by` | 없음 | 인용·원칙 |
| `scene` | `script_file`(또는 `script`), `libs`, `steps`, `html`, `css`, `full`, `caption`, `fallback` | `steps` 값 | GSAP·Canvas·SVG·WebGL·Three.js 로 직접 그리는 장면 (아래 "scene") |
| `end` | `title`, `subtitle`, `asks`(요청·다음 행동 문자열 1~3개) | `asks` 수 | 마지막 장. `asks` 를 주면 `subtitle` 이 작은 머리글(기본 "요청 사항")이 되고 요청이 번호 목록으로 하나씩 나타난다. 없으면 "감사합니다 / Q & A" (린트 경고) |

공통 필드: `transition`, `fx` (아래 "모션"). 알 수 없는 필드는 린트 경고로 알려 준다(오타 방지).

### code 의 세 가지 모드

```jsonc
// ② walk: 스텝마다 지정한 줄만 밝아지고 나머지는 흐려지며, 오른쪽 설명이 따라온다
"code": "…", "walk": [ {"lines": [2, 3], "note": "캐시 확인"}, {"lines": 5, "note": "서명 검증"} ]

// ③ magic: 코드 버전을 순서대로 주면 → 키마다 줄 단위로 모핑한다 (Slidev Magic Move 대응)
//    바뀌지 않은 줄은 새 위치로 미끄러지고, 새 줄은 반짝이며 나타나고, 사라질 줄은 페이드아웃
"magic": [ {"code": "v1…", "note": "기존 방식"}, {"code": "v2…", "note": "교체"}, {"code": "v3…", "note": "캐시 추가"} ]
```
`magic` 은 `code`/`walk` 와 함께 쓸 수 없다. 버전은 2~8개, 버전 사이 변경은 작게(한 번에 3~4줄 이내) 유지해야 모핑이 읽힌다. 12줄 이하의 짧은 코드는 큰 글씨로 표시된다.

## scene — 웹 그래픽으로 직접 그리는 장면

정해진 타입으로 표현하기 어려운 시각화(3D 구성도, 셰이더 배경, 파티클, 맞춤 SVG 애니메이션)를 JS 로 그린다.

```jsonc
{
  "type": "scene",
  "title": "3D 로 본 전체 구성",       // 선택. full 이면 장면 위에 겹쳐 표시
  "script_file": "scenes/topo.js",     // deck.json 기준 상대 경로 (또는 짧은 코드는 "script": "...")
  "libs": ["three", "gsap"],           // 내장: gsap(3.12.5), three(0.170.0, ES 모듈). 순서대로 로드
  "steps": 2,                          // → 키 스텝 수 (0~20). 스크립트의 step(k) 로 전달
  "html": "<div class=\"ov\">…</div>", // 선택. 장면 영역에 들어갈 마크업 (오버레이 글자 등)
  "css": ":scope .ov{left:100px}",     // 선택. :scope 는 이 장면 영역으로 바뀐다
  "full": true,                        // 선택. 여백 없이 슬라이드 전체를 장면으로
  "caption": "…",                      // 선택. 하단 설명
  "fallback": "Three.js 를 불러오지 못했습니다"   // 라이브러리 로드·스크립트 실패 시 보일 문구
}
```

- 그 밖의 라이브러리: `{"name": "d3", "url": "https://…/d3.min.js", "global": "d3"}` (일반 스크립트, `global` 은 전역 이름) 또는 `"module": true` (ES 모듈). 로컬 파일은 `{"name": "x", "src": "vendor/x.js"}` 로 주면 HTML 에 내장돼 **오프라인에서도 동작**한다. CDN 라이브러리는 온라인일 때만 로드되므로 `fallback` 을 꼭 쓴다(없으면 린트 경고)
- `html`·`css`·스크립트는 작성자 코드로 보고 이스케이프하지 않는다. 다른 출처의 문자열을 그대로 넣지 않는다

### 스크립트 작성법

스크립트 본문은 `async function(ctx){ … }` 안에 들어간다(최상위 `await` 가능). 슬라이드를 처음 보여 줄 때 한 번 실행되고, 생명주기 함수를 담은 객체를 `return` 한다. 모두 선택.

```js
const gsap = ctx.lib.gsap;                 // libs 의 name 으로 접근 (three 는 모듈 네임스페이스 = THREE)
const g = ctx.canvas2d();                  // 고해상도 2D 컨텍스트. 좌표는 무대 px (ctx.width × ctx.height)
ctx.loop((t, dt, { k, ts, from }) => { /* 매 프레임: 활성 슬라이드일 때만. t = 진입 후 초, k = 현재 스텝,
                                          ts = 스텝 k 가 시작된 뒤 초, from = 직전 스텝 */ });
return {
  enter() {},                              // 슬라이드에 들어올 때마다
  step(k, still) {},                       // 스텝이 바뀔 때마다 (k = 0..steps). still 이면 애니메이션 없이 최종 상태로
  leave() {},                              // 슬라이드를 떠날 때
  resize(w, h, pixelRatio) {},             // 창 크기가 바뀔 때 (캔버스 크기는 런타임이 이미 맞춤)
  theme(colors) {},                        // t 키로 테마가 바뀔 때
};
```

| `ctx` | 설명 |
|---|---|
| `el` | 장면 영역(div). SVG·DOM 을 여기에 붙인다. 크기는 `ctx.width`, `ctx.height` (무대 px, 1600×900 기준) |
| `lib` | `libs` 로 불러온 라이브러리 |
| `canvas()` | 장면을 덮는 `<canvas>` 를 만들어 준다(WebGL·Three.js 용). 픽셀 크기 = 영역 × `pixelRatio()` |
| `canvas2d()` | 위 캔버스의 2D 컨텍스트, 배율 적용 완료 |
| `pixelRatio()` | 기기 픽셀 비 × 무대 확대율 (최대 2) |
| `loop(fn)` | 프레임 콜백 `fn(t, dt, {k, ts, from})` 등록. 해제 함수를 돌려준다. 그림은 `t`·`k`·`ts`·`from` 으로만 정한다(아래 결정성 규약) |
| `rand(i, salt)` | 결정적 무작위 0~1. 같은 `(i, salt)` 에 늘 같은 값. `Math.random` 대신 쓴다 |
| `noise(t, seed)` | 결정적 잡음 -1~1. `t` 에 대해 부드럽게 변한다(흔들림·떠다님) |
| `theme()` | 현재 테마 색 `{accent, fg, muted, bg, panel, line, edge, name}` |
| `kindColor(kind)` | 노드 종류별 색 (`service`, `db` …) — 토폴로지와 같은 색 |
| `model` | 시스템 모델 `{system, nodes, edges, flows}`. 실제 구성으로 시각화할 때 쓴다 |
| `reduced`, `still` | 동작 줄이기 설정, 정지 화면(스크린샷·PDF) 여부 |

런타임이 대신 해 주는 것:
- **GSAP 정리**: `enter`/`step` 안에서 만든 GSAP 애니메이션은 `gsap.context` 로 모였다가 슬라이드를 떠나면 되돌려진다(다시 들어오면 `enter` 부터 새로). 선택자 문자열은 장면 영역 안에서만 찾는다. 되돌리기 때문에 GSAP 으로 바꾸는 속성은 처음 값을 꼭 갖고 있어야 한다(예: SVG `cx` 없이 `attr:{cx}` 를 트윈하면 빈 값으로 되돌아가 콘솔 에러)
- **정지 화면**: `?still=1`·인쇄·`render_check.py`·`prefers-reduced-motion` 에서는 진행 중인 GSAP 애니메이션을 끝 상태로 보내고, 루프는 `t=1.5` 로 한 프레임만 그린다. `step(k, still)` 에서 `duration: still ? 0 : 1` 처럼 처리하면 확실하다
- **지연 초기화**: 장면은 처음 보일 때 만들어진다(WebGL 컨텍스트 수 제한·로드 시간). 루프는 활성 슬라이드에서만 돈다
- 오버뷰(`o`)에는 캔버스의 현재 픽셀이 복사된다. WebGL 은 `preserveDrawingBuffer: true` 를 줘야 오버뷰·PDF 에 남는다
- **시각 지정**: `deck.seek(i, k, t[, from])` 은 슬라이드 i 에서 스텝 from(기본 k-1)→k 로 넘어간 지 t 초 된 화면을 그리고 멈춘다. GSAP 애니메이션은 일시정지한 채 그 시각으로 옮기고, 루프는 `(t, 0, {k, ts: t, from})` 로 한 번 부른다. 검수·내보내기 도구가 쓴다

### 결정성 규약

장면의 한 프레임은 **`t`, `k`, `ts`, `from` 만으로 정해져야 한다.** 그래야 같은 시각을 다시 찍으면 같은 화면이 나와 검수 스크린샷·PDF·영상 내보내기가 재현되고, 발표 중 앞뒤로 오가도 화면이 어긋나지 않는다.

| 하지 않는다 | 대신 |
|---|---|
| `Math.random()` | `ctx.rand(i, salt)` — 점 i 의 고정된 무작위 값 |
| 프레임마다 위치를 더하기 (`x += v * dt`) | 시각의 함수로 바로 계산 (`x = x0 + v * t`, 화면 밖은 나머지 연산으로 감기) |
| 스텝 전환을 누적 보간 (`x += (tx - x) * dt * k`) | `ts` 로 진행률을 구해 `from` 상태와 `k` 상태 사이를 보간 (`e = ease(ts / 1.2)`) |
| `Date.now()`, `performance.now()`, `setTimeout`, 자체 `requestAnimationFrame` | `ctx.loop` 의 `t`·`ts` |
| GSAP 으로 바꾸는 값의 처음 값을 앞선 애니메이션에 맡기기 | `enter()` 에서 처음 값을 직접 정한다 (`view.r = 24`) |
| CSS `transition`·`@keyframes` 로 장면 안 요소 움직이기 | 루프나 GSAP |

- 빌드 린트가 위 패턴(`Math.random`, 시계, 타이머, `dt` 누적)을 경고한다
- `render_check.py --determinism` 이 장면 슬라이드를 페이지 두 개에서 다른 순서로 같은 (스텝, 시각)에 찍어 비교한다. 다르면 problem 으로 알린다
- 예시 `scenes/voices-canvas.js` 가 이 규약대로 쓴 Canvas 2D 장면이다

예시: `examples/recap/deck-scene.json` 과 `scenes/` (WebGL 셰이더, GSAP+SVG 파이프라인, Canvas 2D 파티클, Three.js 3D 토폴로지).

## 테마

- `aurora` (기본): 검은 배경 위에 천천히 흐르는 블러 그라데이션, 가벼운 큰 제목, 반투명 유리 카드. Slidev 쇼케이스(Neko, antfu)에서 관찰한 인상을 따른다
- `dark`: 격자 배경의 기술 공유용. `light`: 밝은 프로젝터·인쇄용. `toss`: 흰 배경, 블루 포인트, 카드형

`image` 의 `src` 가 로컬 파일이면 빌드 때 HTML 에 base64 로 내장된다(오프라인 유지). 경로는 deck.json 기준 상대 경로이고, 3MB 가 넘으면 경고한다. 원격 URL 은 그대로 두며 이 경우 오프라인에서는 보이지 않는다.

## 모션

| 항목 | 값 | 설명 |
|---|---|---|
| 덱 `transition` / 슬라이드 `transition` | `slide-left`(기본) · `slide-up` · `zoom` · `fade` · `none` | 슬라이드 전환. 방향 인식(뒤로 가면 반대로 움직인다). 슬라이드별 값이 덱 값을 이긴다 |
| 슬라이드 `fx` | `up` · `left` · `right` · `scale` · `fade` | → 키로 요소가 나타나는 방식. 기본값은 타입별: `stats`/`bento`=scale, `terminal`=left, 나머지=up |

항상 적용되는 연출: 제목·핵심 문장의 단어 단위 등장, 스프링 이징(등속 없음), 배경 글로우의 느린 이동, 숫자 카운트업(easeOutQuart), 터미널 명령어 타이핑.
`prefers-reduced-motion` 환경에서는 전환·카운트업·타이핑·패킷 순환을 끄고 최종 상태를 바로 보여 준다.

발표 조작: `o` 전체 슬라이드 보기(클릭하면 이동, `Esc` 닫기), `s` 발표자 노트, `f` 전체화면, `t` 테마.

## 애니메이션 동작

- 모든 토폴로지: 노드가 열 순서대로 나타나고 간선이 그려진다. `async: true` 간선은 점선이 계속 흐른다.
- `topology` + `flow`: 약 1.5초 간격으로 단계가 자동 진행되며 패킷(빛나는 점)이 간선을 따라 이동, 끝나면 처음부터 반복.
- `flow`: → 키마다 한 단계. 현재 단계 간선은 포인트 색으로 그려지고 패킷이 반복 이동, 지난 단계는 흐리게 남는다. `reverse: true` 단계는 패킷이 거꾸로 이동(응답 표현).
- `focus`: 나머지 노드·간선을 흐리게.

## 레이아웃 조정 수단

자동 레이아웃(간선 방향 기준 왼→오 계층)이 어색할 때 순서대로 시도:
1. 해당 슬라이드에 `nodes` 로 부분집합만 그린다
2. 모델 노드에 `tier`(열 번호)를 지정한다
3. 간선 방향을 "요청이 나가는 방향"으로 통일한다(응답은 별도 간선 대신 흐름 단계의 `reverse`)
