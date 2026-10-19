---
name: system-deck
description: 구현한 시스템(저장소)에 대한 발표 장표를 만들 때 사용. 코드베이스·설정·git 이력을 탐색해 시스템 모델(노드/간선/요청 흐름)을 근거와 함께 추출하고, 데이터 흐름이 움직이는 애니메이션 토폴로지가 들어간 단일 HTML 장표를 생성·검수한다. "발표 자료 만들어줘", "아키텍처 장표", "시스템 소개 슬라이드", "구현 회고 발표" 같은 요청에 사용.
---

# system-deck — 시스템 발표 장표 에이전트

결과물: `<repo>/.deck/out/deck.html` (오프라인 동작하는 단일 HTML 장표) + 선택적으로 PDF.
모든 중간 산출물은 `<repo>/.deck/` 아래에 둔다. 저장소의 다른 파일은 절대 수정하지 않는다.

```
.deck/
  scan.json          # 1차 정찰 (scan_repo.py, 결정적)
  system-model.json  # 노드·간선·흐름 + 근거 (system-explorer)
  story.json         # 문제·결정·타임라인·지표 + 출처 (workflow-historian)
  deck.json          # 슬라이드 구성 (이 스킬이 작성)
  out/deck.html, out/shots/*.png, out/deck.pdf
```

스크립트 경로: `S=${CLAUDE_PLUGIN_ROOT}/skills/system-deck/scripts`
(플러그인 밖에서 스킬만 복사해 쓸 때는 이 SKILL.md 옆의 `scripts/`.)

---

## 1단계 — 발표 맥락 확정

사용자 입력에서 아래를 뽑는다. **빠진 것만** AskUserQuestion 한 번으로 묻는다(최대 4문항). 이미 답이 있으면 묻지 않는다.

| 항목 | 기본값 | 장표에 미치는 영향 |
|---|---|---|
| 청중 | 사내 비개발 직군 + 경영진 | 용어 수준, 코드 슬라이드 개수 |
| 발표 시간 | 10분 | 슬라이드 수 (분당 1장 내외) |
| 강조점 | 아키텍처와 요청 흐름 | 흐름(flow) 슬라이드 선택 |
| 테마 | `aurora` | `aurora` / `dark` / `light` / `toss` |

청중이 비개발자 중심이면 코드 슬라이드는 0~1장, 기술 용어는 첫 등장 시 한 줄 풀이를 붙인다.

## 2단계 — 1차 정찰 (결정적)

```bash
mkdir -p <repo>/.deck && python3 $S/scan_repo.py <repo> -o <repo>/.deck/scan.json
```

결과 요약(진입점·연동·compose 서비스 수)을 확인한다. 스캔은 단서일 뿐 결론이 아니다.

### 2-b. 문서 인제스천 (입력에 문서 파일이 있을 때만)

기획서·보고서·발표 자료 등 문서가 함께 주어지면 Markdown 과 표 JSON 으로 변환한다.

```bash
python3 $S/ingest.py <문서1> <문서2 | 폴더> -o <repo>/.deck
```

- `.deck/source.md` — 본문. 표 앞에 `> [표 N · 파일명]` 표식이 있어 출처로 인용할 수 있다
- `.deck/source-tables.json` — 표별 `header/rows/numeric_cols` 와 추천 슬라이드 타입(`suggest`)
- `.hwpx` 는 의존성 없이 직접 파싱한다. 바이너리 `.hwp` 는 `pip install pyhwp` 가 필요하고 표가 사라지므로 한글에서 `.hwpx`/PDF 로 저장해 다시 달라고 안내한다. PDF·PPTX·DOCX·XLSX 는 `pip install "markitdown[all]"` 이 필요하다
- "추출된 텍스트가 없음"은 스캔 이미지 PDF 다. OCR 은 이 플러그인 범위 밖이라고 알리고 멈춘다
- 문서만 있고 저장소가 없으면 3단계의 `system-explorer` 는 건너뛰고(토폴로지 슬라이드 없음) `story.json` 만 만든다. 이 경우 `deck.json` 의 `model` 은 `{"nodes": [], "edges": []}` 로 두고 `topology`/`flow` 타입을 쓰지 않는다. `title` 타입은 빈 토폴로지로도 동작한다

**표 → 슬라이드 변환 규칙** (`source-tables.json` 의 `suggest` 를 출발점으로 한다)

| 표 성격 | 슬라이드 | 매핑 |
|---|---|---|
| 지표·수치 비교(숫자 열 있음, 행 ≤4) | `stats` | 값 셀 → `value`, 행 이름 → `label`, 상대 크기 → `bar`(0~100) |
| 시기가 첫 열(월·분기·단계) | `timeline` | 첫 열 → `period`, 나머지 → `title`/`detail` |
| 점검·검증 결과(통과/실패 열) | `terminal` | 상태 열 → `status`, 비고 → `detail` |
| 2열 대조(전/후, 현행/개선) | `split` | 열 제목 → `left.title`/`right.title` |
| 항목 3~4개와 설명 | `bento` | 항목 → `title`, 설명 → `body` |
| `excerpt` (13행 이상, 9열 이상, 빈 칸 40% 초과 — 예산표·코드표·조사기준표) | `bullets`/`stats` | 슬라이드로 옮기지 않는다. 발표 주제와 관련된 핵심 행 3~4개만 발췌하고 나머지는 "상세는 문서 표 N" 로 돌린다 |
| 그 외 큰 표 | `bullets` | 핵심 행만 요약. 표 전체를 옮기지 않는다 |

`번호`·`순번`·`계급`·`코드` 열은 숫자처럼 보여도 지표가 아니므로 `stats` 의 값으로 쓰지 않는다. 가로 병합 셀은 첫 칸에만, 세로 병합 셀은 아래 칸에도 같은 글이 들어간다. 입력 안내 문구·머리말·각주는 `ctrl` 로 분류돼 본문에서 제외된다(각주 내용은 보존되지 않는다).

변환한 모든 수치에는 `source`(예: `"기획서.hwpx 표 2"`)를 붙인다. 표에 없는 숫자는 만들지 않는다.

## 3단계 — 병렬 심층 탐색 (서브에이전트 2개를 한 메시지에서 동시에 실행)

- **system-explorer** → `.deck/system-model.json`
  프롬프트에 저장소 경로, scan.json 경로, 발표 강조점, 그리고 `references/model-schema.md` 경로를 넘긴다.
- **workflow-historian** → `.deck/story.json`
  프롬프트에 저장소 경로, scan.json 경로, 발표 맥락을 넘긴다. `.deck/source.md` 가 있으면 경로를 함께 넘겨 문서 내용도 출처(`"파일명 표 N"`, `"파일명 §제목"`)로 쓰게 한다.

둘 다 끝나면 모델을 검증한다:

```bash
python3 - <<'EOF'
import json; m=json.load(open('<repo>/.deck/system-model.json'))
print(len(m['nodes']),'nodes',len(m['edges']),'edges',[f['id'] for f in m['flows']])
EOF
```

노드가 14개를 넘으면 발표용으로 과하다. 전체 토폴로지 슬라이드는 핵심 노드만(`nodes` 필드로 부분집합) 보여 주고, 세부는 `focus` 슬라이드로 나눈다.

## 4단계 — 장표 구성 (`deck.json` 작성)

`references/deck-schema.md`(슬라이드 타입·필드)와 `references/storytelling.md`(구성 규칙·문장 톤)를 읽고 작성한다.

기본 뼈대 (10분 기준 9~12장):

1. `title` — 배경에 토폴로지가 은은하게 움직인다
2. `bullets` — 왜 만들었나 (story.problem, story.constraints)
3. `topology` + `flow` 지정 — 전체 구성, 대표 흐름이 자동 순환 애니메이션
4. `flow` — 대표 요청 흐름을 → 키로 한 단계씩 (가장 중요한 1~2개만)
5. `topology` + `focus` — 설계 포인트별 확대 (story.decisions 와 짝)
6. `code` — 결정적 코드 1~2개 (근거 파일:라인 그대로 발췌, 20줄 이하). 단계별 설명은 `walk`, 리팩터링 전후는 `magic`(줄이 미끄러지며 변형)
7. `split` 또는 `bullets` — 구현 타임라인 (story.timeline)
8. `stats` — 결과/지표 (story.metrics 에 출처가 있는 숫자만)
9. `bullets` — 남은 과제
10. `end`

**모션 연출** (`references/deck-schema.md` 의 "모션" 절): 장표가 평면적으로 느껴지지 않게 아래를 쓴다. 단, 장식이 메시지를 가리면 뺀다.

- 핵심 메시지 1개는 `statement` 로 한 문장만 크게. 덱 전체에서 1~2장
- 실제 화면(대시보드, 관리 콘솔, 결과 화면)이 있으면 추상 도형보다 `image` + `marks` 로 보여 준다. 캡처는 사용자가 준 파일이나 저장소의 `docs/`·`assets/` 이미지만 쓰고, 없는 화면을 만들어 내지 않는다
- 시스템 점검·검증 결과는 `terminal`, 정량 변화는 `stats`(+`bar`), 3~4가지 효과는 `bento`, 일정은 `timeline`
- 전환은 기본 `slide-left`. 장 전환·전환점 슬라이드만 `zoom`/`slide-up` 으로 바꿔 리듬을 만든다 (한 덱에서 3종 넘게 섞지 않는다)
- 기존 타입으로 안 되는 시각화(3D 구성도, 셰이더 배경, 맞춤 SVG 애니메이션, 파티클)는 `scene` 으로 직접 그린다. 스크립트는 `.deck/scenes/*.js` 에 두고 `script_file` 로 참조한다. 덱 전체에서 1~2장, 데이터는 `ctx.model` 등 근거 있는 것만 쓴다. CDN 라이브러리(`gsap`, `three`)는 오프라인에서 안 보이므로 `fallback` 을 쓰고, 오프라인 발표면 라이브러리를 `.deck/vendor/` 에 받아 `{"name", "src"}` 로 내장한다
- 같은 타입 슬라이드가 3장 연속 나오지 않게 순서를 섞는다
- 스텝(→) 수는 슬라이드당 2~5. 7을 넘으면 슬라이드를 쪼갠다

**사실 규칙**: 장표의 모든 사실 문장은 system-model 의 `evidence` 또는 story 의 `source` 로 거슬러 올라갈 수 있어야 한다. 근거 없는 숫자(성능 향상 %, 사용자 수 등)는 만들지 않는다. 필요한데 없으면 `"[확인 필요: ...]"` 자리표시로 남기고 마지막에 사용자에게 목록으로 알린다.

`notes`(발표자 노트)는 슬라이드마다 1~3문장 작성한다. 발표 중 `s` 키로 볼 수 있다.

## 5단계 — 빌드와 시각 검수 (최대 3회 반복)

```bash
python3 $S/build_deck.py <repo>/.deck/deck.json -o <repo>/.deck/out/deck.html
python3 $S/render_check.py <repo>/.deck/out/deck.html --shots <repo>/.deck/out/shots
```

- `build_deck.py` 는 필드 오류(필수 필드 누락, 범위 밖 값)는 실패로, 린트 경고(제목 28자·본문 45자 초과, 강조 남용, 발표자 노트 없음, `terminal`/`stats` 항목의 `source` 없음, 오타 필드)는 stderr 로 알린다. 경고도 모두 고친다. 전부 해소됐는지 `--strict` 로 확인한다
- `problems` 가 비어 있지 않으면 고친다. `warnings` 의 CDN 로드 실패는 오프라인 환경이면 무시한다.
- **스크린샷을 Read 로 직접 열어** topology/flow 슬라이드를 하나씩 본다. 확인 항목:
  - 간선 라벨이 노드나 다른 라벨을 가리지 않는가 → 라벨을 짧게(2~3단어), 또는 노드 수를 줄인다
  - 노드 이름이 말줄임(…)으로 잘렸는가 → `label` 은 10자 안팎, 세부는 `tech` 로
  - 한 계층에 노드가 6개를 넘어 납작해졌는가 → `nodes` 부분집합 슬라이드로 분리
  - 흐름이 지그재그로 꼬였는가 → 해당 노드에 `tier` 를 명시해 열 위치를 고정
- playwright 가 없으면 `pip install playwright && python -m playwright install chromium` 을 안내하고, 설치가 불가하면 검수 단계를 건너뛰었다고 명시한다.

## 6단계 — 독립 사실 검증

**deck-reviewer** 서브에이전트(작업 과정을 보지 않은 새 에이전트)에게 `deck.json`, `system-model.json`, `story.json`, 저장소 경로를 주고 검증시킨다. 반환된 `unsupported` 항목은 고치거나 장표에서 뺀다. 고친 뒤 5단계 빌드를 한 번 더 돌린다.

## 7단계 — 전달

- 필요 시 PDF: `python3 $S/render_check.py <html> --pdf <repo>/.deck/out/deck.pdf`
- 제출용 PPTX: `python3 $S/export_pptx.py <html> -o <repo>/.deck/out/deck.pptx` (`pip install python-pptx playwright`). 슬라이드마다 최종 상태 이미지와 발표자 노트가 들어가며 모션과 텍스트 편집은 되지 않는다. 사용자에게 이 한계를 한 줄로 알린다
- 사용자에게: 결과 파일 경로, 슬라이드 수, `[확인 필요]` 목록, 발표 조작법 한 줄
  (→/Space 다음 · ← 이전 · `o` 전체 보기 · `s` 발표자 노트 · `f` 전체화면 · `t` 테마 전환 · 브라우저 인쇄로 PDF)
- 진행 과정 요약은 하지 않는다.

## 장표 수정 요청이 왔을 때

`.deck/deck.json` 이나 `system-model.json` 만 고치고 5단계부터 다시 돌린다. HTML 을 직접 손대지 않는다(다음 빌드에서 덮어써진다).
