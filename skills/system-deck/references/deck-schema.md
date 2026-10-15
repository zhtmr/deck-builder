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
| `end` | `title`, `subtitle` | 없음 | 마지막 장 |

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
