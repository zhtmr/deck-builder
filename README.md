# deck-builder

구현한 시스템의 코드베이스와 git 이력을 탐색해, **데이터 흐름이 움직이는 애니메이션 토폴로지**가 들어간 발표 장표(단일 HTML)를 만들어 주는 Claude Code 플러그인입니다.

## 설치

```bash
# 압축을 푼 폴더 기준
/plugin marketplace add zhtmr/deck-builder
/plugin install deck-builder@deck-builder-local
```

장표 검수(스크린샷·넘침 검사·PDF)에는 playwright 가 필요합니다.

```bash
pip install playwright && python -m playwright install chromium
```

## 사용

```
/deck-builder:present                      # 현재 저장소, 맥락은 질문으로 받음
/deck-builder:present ../recap 경영진 대상 10분, toss 테마, 비동기 구조 강조
```

결과는 대상 저장소의 `.deck/out/deck.html` 에 생깁니다 (`.deck/` 는 `.gitignore` 에 추가 권장).

발표 조작: `→`/`Space` 다음 · `←` 이전 · `o` 전체 보기 · `s` 발표자 노트 · `f` 전체화면 · `t` 테마 전환(dark → light → toss) · 브라우저 인쇄로 PDF · 모바일은 스와이프

## 구성

```
deck-builder/
├─ .claude-plugin/plugin.json, marketplace.json
├─ commands/present.md            # /deck-builder:present
├─ agents/
│  ├─ system-explorer.md          # 코드·설정 → system-model.json (노드/간선/흐름 + 파일:라인 근거)
│  ├─ workflow-historian.md       # git 이력·문서 → story.json (문제·결정·타임라인·지표 + 출처)
│  └─ deck-reviewer.md            # 완성 장표의 사실 문장을 원문과 독립 대조
└─ skills/system-deck/
   ├─ SKILL.md                    # 7단계 오케스트레이션
   ├─ references/                 # 모델·장표 스키마, 발표 구성·문장 규칙
   ├─ scripts/
   │  ├─ scan_repo.py             # 결정적 1차 정찰 (Spring/FastAPI/Express/compose/k8s/git)
   │  ├─ ingest.py                # 문서(HWPX/PDF/PPTX/DOCX/MD) → source.md + 표 JSON
   │  ├─ export_pptx.py           # 장표 → 이미지 PPTX (발표자 노트 포함)
   │  ├─ build_deck.py            # deck.json + model → HTML (검증·린트 포함, 표준 라이브러리만 사용)
   │  ├─ deck_template.html       # 슬라이드 엔진 + 토폴로지 애니메이션 (외부 의존성 없음)
   │  └─ render_check.py          # 헤드리스 검수: 스크린샷, 넘침, 콘솔 에러, PDF
   └─ examples/recap/             # 예시 모델·장표와 빌드 결과
```

## 동작 흐름

1. 발표 맥락(청중·시간·강조점·테마) 확정 — 빠진 것만 질문
2. `scan_repo.py` 로 진입점·연동·설정·배포·git 이력 1차 정찰
3. `system-explorer` 와 `workflow-historian` 병렬 실행
4. 스키마와 구성 규칙에 맞춰 `deck.json` 작성
5. 빌드 → 헤드리스 스크린샷을 직접 보고 겹침·잘림 수정 (최대 3회)
6. `deck-reviewer` 가 근거 없는 주장·코드 불일치 검출 → 수정
7. HTML(+PDF) 전달, `[확인 필요]` 목록 보고

## 문서도 입력으로

저장소 대신(또는 함께) 문서를 주면 먼저 Markdown 과 표 JSON 으로 변환하고, 표는 `stats`/`timeline`/`terminal`/`bento` 슬라이드로 바꿉니다.

```
/deck-builder:present ../recap 기획서.hwpx 보고서.pdf 경영진 대상 10분
python skills/system-deck/scripts/ingest.py 기획서.hwpx -o .deck      # 변환만 따로 할 때
```

| 형식 | 처리 |
|---|---|
| `.hwpx` | 내장 파서(의존성 없음). 문단·표·중첩 표 |
| `.hwp` | `pip install pyhwp` (표 보존 안 됨 — `.hwpx`/PDF 로 저장 권장) |
| `.pdf .pptx .docx .xlsx` | `pip install "markitdown[all]"` |
| `.md .txt` | 그대로 |

스캔 이미지 PDF 는 텍스트가 없어 변환되지 않습니다(OCR 미지원).

## 슬라이드 타입

`title` · `section` · `bullets` · `topology`(자동 순환 흐름, 포커스, 부분집합) · `flow`(한 단계씩 패킷 이동 + 단계 패널) · `code`(라인 강조 / `walk` 단계 포커스 / `magic` 줄 모핑) · `split` · `stats`(숫자 카운트업 + 비교 막대) · `terminal`(타이핑 + 진행 막대 + `[OK]` 배지) · `bento` · `timeline` · `image`(스크린샷 + 단계별 하이라이트 박스) · `statement` · `quote` · `end`
자세한 필드는 `skills/system-deck/references/deck-schema.md`. 데모: `skills/system-deck/examples/recap/deck-motion.html`.

## 모션

슬라이드 전환(`slide-left`/`slide-up`/`zoom`/`fade`, 방향 인식), 스텝 등장 프리셋(`up`/`left`/`right`/`scale`/`fade`), 제목의 단어 단위 등장, 스프링 이징, 코드 매직무브, 숫자 카운트업, 터미널 타이핑, 천천히 흐르는 배경 글로우, `o` 키 전체 슬라이드 보기를 지원합니다. `prefers-reduced-motion` 에서는 모션을 끄고 최종 상태를 보여 줍니다.

## 내보내기

- PDF: 브라우저 인쇄 또는 `render_check.py --pdf`
- PPTX: `python skills/system-deck/scripts/export_pptx.py deck.html` — 슬라이드별 최종 상태 이미지 + 발표자 노트(모션·텍스트 편집 불가, 제출용)

## 테스트

```bash
python -m unittest discover -s tests
```

## 테마

- `aurora` — 기본. 검은 배경 + 천천히 흐르는 블러 그라데이션, 가벼운 큰 제목, 유리 카드 (Slidev 쇼케이스 Neko·antfu 덱을 참고, `slidev_25.md`)
- `dark` — 격자 배경의 기술 공유용
- `light` — 밝은 프로젝터·인쇄용
- `toss` — 흰 배경, 블루 포인트(#3182f6), 큰 굵은 타이포, 카드형 불릿. Toss Product Sans 는 비공개 서체라 Pretendard 로 대체하며, 로고·상표는 넣지 않습니다.

## 오프라인

결과 HTML 은 인터넷 없이 동작합니다. 온라인일 때만 Pretendard 웹폰트와 코드 하이라이트(highlight.js)를 CDN 에서 불러오고, 없으면 시스템 한글 폰트와 무채색 코드로 표시됩니다.
