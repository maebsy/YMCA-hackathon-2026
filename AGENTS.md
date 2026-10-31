# AI 에이전트 작업 규칙

Claude Code·Codex·Cursor 같은 AI 코딩 에이전트가 이 저장소에서 **작업을 시작하기 전에 읽는** 팀 규칙입니다. 사람도 같은 규칙을 따릅니다.

5명이 각자 에이전트로 동시에 작업합니다. 핵심은 하나입니다. **내 작업 범위만 고치고, 남의 영역은 고치지 말고 알린다.**

- 폴더 안에 `AGENTS.md`가 따로 있으면 그 폴더 규칙도 함께 따릅니다.
- 이슈·브랜치·커밋·PR 형식은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다. 대부분 훅과 CI가 자동으로 검사합니다.
- 문서 위치는 [docs/README.md](docs/README.md)에 정리돼 있습니다.

## 0. 서비스 한 줄

**72hours**: AI로 사이트를 만든 비개발자가 공개 GitHub 저장소 주소를 넣으면, 보안엔진이 취약점을 찾고 GPU 서버의 LLM이 쉬운 설명과 수정 지시를 만들어 대시보드와 MCP로 AI 코딩툴에 넘깁니다. 고친 뒤 재검사해 완료 리포트를 주고, 사고가 의심되면 신고서 초안 작성을 돕습니다.

```
GitHub 주소 → security_engine 검사 → backend /api/scans → GPU LLM 해석 /api/llm/*
           → frontend 대시보드 → MCP로 AI 코딩툴에 전달 → 재검사 → 리포트 /api/reports/*
```

## 1. 작업 시작 전 (매번)

1. **최신 main에서** 브랜치를 만듭니다.
   ```bash
   git fetch origin
   git switch -c <타입>/<이슈번호>-<짧은-설명> origin/main
   ```
2. **이슈 하나 = 브랜치 하나 = PR 하나.** 이슈가 없으면 먼저 만듭니다.
3. 고칠 파일이 [2장 영역 지도](#2-영역-지도)에서 누구 담당인지 확인합니다. 남의 영역이면 [4장](#4-작업-범위)을 따릅니다.
4. **같은 파일을 고치는 다른 브랜치가 있는지** 확인합니다. 겹치거나 충돌하면 그 작성자와 먼저 이야기합니다. PR을 올리기 직전에도 한 번 더 실행합니다.
   ```bash
   bash scripts/check-overlap.sh
   ```
   머지 안 된 원격 브랜치마다 나와 겹치는 파일과 실제 충돌 여부를 보여 줍니다. 오래 멈춘 브랜치는 따로 표시합니다.

## 2. 영역 지도

| 경로 | 하는 일 | 담당 (리뷰어) |
|---|---|---|
| `security_engine/`, `tests/security/` | 스캐너 3종(Opengrep·OSV-Scanner·Gitleaks)과 자체 설정 검사기 실행, 결과 정규화, 재검사 비교 | 장양환 `@surilog` |
| `backend/app/llm/`, `backend/app/explain_jobs/`, `scripts/llm/`, `deploy/llm-jobs/` | GPU LLM 해석(문맥 분석·SSVC 위험도·Blue–Red), 비동기 해석 작업 | 유영민 `@maebsy` |
| `backend/app/routers/scans.py`, `backend/app/scan_store.py`, `backend/app/db.py`, `backend/app/models.py` | 검사 API, 검사 결과 저장 | 김건우 `@papawolf42`, 유영민 `@maebsy` |
| `docs/db-*`, `docs/migrations/`, `docs/scan-persistence.md`, `tests/db/` | DB 설계·스키마·저장 절차 | 김건우 `@papawolf42` |
| `backend/app/reports/`, `backend/app/routers/reports.py` | 비전공자용 리포트, 신고서 초안 | 박기태 `@SeouliteParker` |
| `frontend/` | Next.js 대시보드 | 조은익 `@nick19850906-debug` |
| `integrations/mcp-handoff/` | 검사 결과·수정 지시를 AI 코딩툴에 넘기는 MCP 서버 | 유영민 `@maebsy` |
| `deploy/general-server/`, `compose*.yaml`, `.github/`, `.githooks/`, `scripts/` | 서버 배포, 개발 환경, CI·훅 | 유영민 `@maebsy` |
| `docs/system-flow.*`, `docs/competitors*.md`, `docs/roadmap.md`, `docs/submission/` | 기획·경쟁사·발표·제출 | 박기태 `@SeouliteParker` |
| `backend/app/main.py`, `backend/app/config.py`, `.env.example` | 여러 영역이 함께 쓰는 진입점·설정 | 유영민 `@maebsy`, 김건우 `@papawolf42` |

- 담당은 2026-10-31까지의 git 기록으로 정한 초안입니다. 바꾸려면 이 표와 [.github/CODEOWNERS](.github/CODEOWNERS)를 같은 PR에서 고칩니다.
- CODEOWNERS에는 영역마다 보조 리뷰어를 1명 더 넣었습니다. 담당자 본인이 PR을 올려도 리뷰 요청이 가고, 둘 중 깨어 있는 사람이 승인하면 됩니다.
- 담당자는 그 영역 PR의 리뷰어이자, 다른 사람이 그 영역을 고쳐야 할 때 먼저 물어볼 사람입니다.

## 3. 계약 파일

한쪽이 바꾸면 다른 영역이 조용히 깨지는 파일입니다.

| 계약 | 정하는 파일 | 쓰는 쪽 |
|---|---|---|
| 보안엔진 결과 JSON | `security_engine/schema/scan_result.schema.json`, `security_engine/models.py` | `backend/app/llm/engine_adapter.py`, `backend/app/routers/scans.py` |
| LLM 해석 요청·응답 | `backend/app/llm/schemas.py` | `frontend/src/types/security.ts`, `frontend/src/lib/api.ts`, `integrations/mcp-handoff/` (`ai_fix_prompt`) |
| 검사 API 응답 | `backend/app/routers/scans.py` | `frontend/src/lib/api.ts`, `frontend/src/components/tabs/ReportTab.tsx` |
| 리포트·신고서 API | `backend/app/reports/schemas.py` | `frontend/src/components/tabs/ReportTab.tsx`, `IncidentTab.tsx` |
| MCP 도구 이름 | `integrations/mcp-handoff/server.py` (`list_findings`, `get_fix_prompt`, `fix_finding`) | `frontend/src/lib/mcp.ts`, `frontend/src/components/McpHandoff.tsx`, `WorkspaceTab.tsx` |
| DB 스키마 | `docs/db-schema.sql`, `docs/migrations/` | `backend/app/explain_jobs/store.py`, `backend/app/scan_store.py` |
| 환경 변수 이름 | `backend/app/config.py`, `backend/app/explain_jobs/config.py` | `.env.example`, `deploy/general-server/*.env.example`, `compose.yaml` |

- **필드 추가**는 괜찮습니다. **이름 바꾸기·삭제·의미 변경**은 쓰는 쪽 담당자의 승인을 받고, 같은 PR에서 양쪽을 함께 고칩니다.
- 실제로 있었던 일: #63에서 화면의 MCP 도구 이름(`get_fix_task`)이 서버(`get_fix_prompt`)와 달라 연결이 깨졌습니다.
- 기능 동결 뒤에는 계약을 바꾸지 않습니다.

## 4. 작업 범위

- **이슈에 적힌 일만 합니다.** "하는 김에" 하는 리팩터링, 포맷 정리, 이름 바꾸기, 파일 이동, 의존성 업그레이드는 하지 않습니다.
- **남의 영역 파일을 고쳐야 하면** 고치지 말고 PR 본문의 "다른 영역 요청"에 적은 뒤 담당자를 멘션하거나 이슈를 만듭니다. 라우터 등록 한 줄 같은 연결 코드는 예외지만, PR 본문에 적습니다.
- 테스트를 통과시키려고 기존 테스트를 지우거나 기대값을 바꾸지 않습니다. 테스트가 틀렸다고 판단하면 이유를 PR 본문에 씁니다.
- 다른 사람이 남긴 주석·문서의 결정 사항을 지우지 않습니다.
- **변경은 300줄 이하**를 권장합니다(테스트·lock 파일 제외). 넘으면 나눕니다.
- **같은 작업을 새 브랜치로 다시 만들지 않습니다.** v2·v3 브랜치 대신 원래 PR에 커밋을 더하거나 내 브랜치를 rebase 합니다. 다른 사람 브랜치에는 push하지 않습니다.
- **아직 머지 안 된 PR 위에 다음 PR을 쌓지 않습니다.** Squash 머지라서 쌓은 PR은 앞 PR이 머지되는 순간 거의 항상 충돌합니다. 기다리거나 하나로 합칩니다.

## 5. 충돌이 잦은 파일

main에 머지된 PR 29개 중 `docs/external-resources.md`를 14개, `README.md`를 9개, `backend/app/main.py`와 `.env.example`을 각각 7개가 고쳤습니다(2026-10-31 기준).

| 파일 | 규칙 |
|---|---|
| `docs/external-resources.md` | **관련 있는 행 바로 아래에** 행만 추가합니다. 표 맨 끝에 몰아 넣지 않습니다. 정렬·기존 행 수정 금지(버전이 바뀐 행만 고침) |
| `backend/app/main.py` | 라우터 등록 한 줄만 추가합니다. 순서 바꾸기·정리 금지 |
| `backend/app/routers/scans.py` | 고치기 전에 팀 채팅에 알립니다. 새 기능은 새 모듈로 만들고 여기서는 불러오기만 합니다 |
| `.env.example`, `deploy/general-server/*.env.example` | 관련 구역 끝에 설명 주석과 함께 추가합니다. 기존 줄 재배치 금지 |
| `README.md` | 자기 구역만 고칩니다. 맨 위 서비스 소개는 프론트·발표 담당이 관리합니다 |
| `frontend/src/app/page.tsx`, `frontend/src/components/tabs/*.tsx` | 큰 파일입니다. 포맷만 바뀌는 diff 금지, 새 컴포넌트는 새 파일로 |
| `frontend/package-lock.json` | 손으로 고치지 않습니다. 충돌 나면 main 쪽을 받고 `npm install`을 다시 실행합니다 |
| `compose.yaml` | 서비스 추가만 합니다. 기존 서비스 설정 변경은 인프라 담당 리뷰를 받습니다 |

## 6. 검증 명령

PR을 올리기 전에 바꾼 영역의 명령을 실행하고, 결과를 PR 본문에 붙입니다. 모두 저장소 루트에서 시작합니다.

| 바꾼 곳 | 명령 |
|---|---|
| `backend/` | `cd backend && python -m pytest -q` |
| `security_engine/` | `python -m pip install -r tests/security/requirements.txt` 후 `python -m pytest tests/security -q` |
| `frontend/` | `cd frontend && npm ci && npm run lint && npm run build` |
| `integrations/mcp-handoff/` | [README](integrations/mcp-handoff/README.md)대로 전용 venv를 만든 뒤 `python -m unittest discover -s integrations/mcp-handoff/tests -v` |
| `deploy/general-server/` | `python -m pytest deploy/general-server/tests -q` |
| 파이썬 전체 (CI `lint`와 같음) | `pipx run ruff check --select E9,F63,F7,F82 .` |

2026-10-31 main 기준: backend 233개 통과(44개는 PostgreSQL이 없어 건너뜀), security 23개 통과(6개는 스캐너가 없어 건너뜀), deploy 3개 통과, frontend lint·build 통과. 건너뛴 테스트를 실패로 바꾸지 않습니다.

## 7. PR 올리기 전

1. `git fetch origin && git rebase origin/main`(또는 `git merge origin/main`) 후 검증 명령을 다시 실행합니다.
2. PR 본문 양식을 채웁니다. 특히 **어떻게 확인했나요**(실행한 명령과 결과), **다른 영역 요청**, **AI가 한 일**을 적습니다.
3. 새 외부 자원(라이브러리·모델·데이터셋·API·AI 도구)을 썼다면 같은 PR에서 `docs/external-resources.md`에 추가합니다. **빠지면 실격**입니다.
4. 리뷰어는 CODEOWNERS가 자동으로 지정합니다. 지정되지 않으면 영역 지도의 담당자를 직접 지정합니다.

## 8. 하면 안 되는 것

- `.env`, API 키, 토큰, 서버 주소·계정, 개인정보(전화번호 등)를 커밋하거나 PR 본문·로그에 출력하기
- `docs_ignore/` 같은 로컬 전용 폴더를 `git add` 하기
- `--no-verify`로 훅 건너뛰기, main에 직접 push, 남의 브랜치에 push·force push
- **팀이 정하지 않은 값을 지어 넣기**: 가격, 사용량 한도, 성능 수치, 고객 수, 파트너사 이름 등. 모르면 "결정 필요" 또는 `[확인 필요]`로 남깁니다
- **코드에 없는 기능을 있는 것처럼 쓰기**: README, 화면 문구, 발표 자료는 심사 대상입니다. 구현 안 된 기능은 "계획"이라고 씁니다

## 9. 글쓰기

- 사용자는 비개발자입니다. 화면·리포트 문구는 전문 용어를 풀어서 씁니다.
- 문서와 주석은 한국어, 코드 식별자는 영어로 씁니다. 주석 양과 말투는 주변 코드에 맞춥니다.
- 결정된 것과 제안을 구분합니다. 확정이 아니면 "제안", "초안"이라고 적습니다.

## 10. 기능 동결 뒤

- 동결 시각과 머지 순서는 팀이 정해 채팅으로 공지합니다. 계획 초안: [docs/submission/README.md](docs/submission/README.md)
- 동결 뒤에는 **시연 경로의 P0 버그 수정만** 합니다. `hotfix/` 브랜치를 쓰고, 새 기능·리팩터링·의존성 추가는 하지 않습니다.
- 머지는 머지 담당 1명이 순서대로 합니다. 나머지는 main이 바뀔 때마다 자기 브랜치를 rebase 합니다.
