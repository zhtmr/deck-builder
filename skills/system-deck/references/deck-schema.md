# deck.json 명세

```jsonc
{
  "title": "장표 제목", "subtitle": "부제", "eyebrow": "제목 위 작은 문구",
  "author": "이름 · 역할", "date": "2026.10",
  "theme": "dark",            // dark | light | toss
  "accent": "#7dd3fc",        // 선택. 생략하면 테마 기본값 (toss = #3182f6)
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
| `code` | `file`, `lang`, `code`, `start_line`, `highlight`(라인 번호 목록), `points`(오른쪽 설명 3개 이하) | 없음 | 20줄 이하 발췌 |
| `split` | `left:{title, bullets}`, `right:{title, bullets}` | 없음 | 비교, 전/후, 타임라인 |
| `stats` | `items:[{value, label, hint}]` (1~4개) | 항목 수 | 결과 지표 |
| `end` | `title`, `subtitle` | 없음 | 마지막 장 |

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
