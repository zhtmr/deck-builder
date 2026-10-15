---
description: 현재(또는 지정한) 저장소를 탐색해 애니메이션 토폴로지가 들어간 시스템 발표 장표(HTML)를 만든다
argument-hint: "[저장소 경로] [발표 주제·청중·시간 등 자유 메모]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion
---

`system-deck` 스킬의 절차를 그대로 따라 발표 장표를 만든다.

입력: $ARGUMENTS

- 첫 번째 인자가 존재하는 디렉터리면 그것을 대상 저장소로, 아니면 현재 작업 디렉터리를 대상으로 한다.
- 나머지 텍스트는 발표 맥락(청중, 발표 시간, 강조하고 싶은 부분, 테마 등)으로 취급한다.

먼저 `${CLAUDE_PLUGIN_ROOT}/skills/system-deck/SKILL.md` 를 읽고 1단계부터 진행한다.
