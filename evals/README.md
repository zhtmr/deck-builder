# 평가 (evals)

SKILL.md 나 에이전트 프롬프트를 고친 뒤, 같은 요청을 다시 돌려 결과가 나빠지지 않았는지 확인한다. `tests/` 는 스크립트 단위 테스트이고, 여기는 **스킬 전체를 한 번 실행한 결과**를 본다.

## 실행

1. `evals.json` 에서 평가 하나를 고르고 `target` 대로 대상 폴더를 준비한다 (`files` 가 있으면 복사)
2. 대상 폴더에서 새 Claude Code 세션을 열고 플러그인을 설치한 뒤 `prompt` 를 그대로 보낸다
3. 질문이 오면 `brief_answers` 대로만 답한다
4. 끝나면 자동 판정을 돌린다

```bash
python3 evals/check_deck.py <대상 폴더>/.deck <check 값>
# 예: python3 evals/check_deck.py /tmp/eval-1/.deck --slides 9-12 --repo /tmp/eval-1
```

5. `assertions` 는 사람이 transcript 와 장표(`out/sheet*.png`, 최종 보고)를 보고 하나씩 판정한다

## 자동 판정 항목 (check_deck.py)

| 항목 | 확인 |
|---|---|
| `outline` | `outline.md` 에 핵심 메시지와 제목 표 |
| `strict_build` | `build_deck.py --strict` 통과 (린트·리듬 경고 0) |
| `titles_from_outline` | 장표 제목이 아웃라인 그대로 |
| `end_asks` | 마지막 장이 `end` + `asks` |
| `slide_count` / `no_code` / `doc_only` | 분량, 비개발 청중, 문서만 입력 |
| `html` / `sheets` | 빌드 결과와 검수 시트가 있다 |
| `critique` / `independent_critique` | 비평 기록과 deck-critic 판정을 옮겨 적은 기록 |
| `repo_untouched` | 대상 저장소에서 `.deck/` 밖이 바뀌지 않았다 |

결과는 평가 이름과 날짜로 기록해 두고(예: PR 설명), 이전 결과와 비교한다.
