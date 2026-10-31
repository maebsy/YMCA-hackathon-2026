# 문서 지도

어떤 문서가 어디 있는지 한곳에 모았습니다. 새 문서를 만들면 이 표에 한 줄 추가합니다.
파일 위치는 다른 PR과 충돌하지 않도록 옮기지 않았습니다. 찾을 때는 이 표를 먼저 봅니다.

## 처음 보는 사람

| 문서 | 내용 |
|---|---|
| [README.md](../README.md) | 서비스 소개, 실행 방법 |
| [docs/system-flow.md](system-flow.md) | 서비스 흐름과 시스템 구성 (설계 기준). 그림 버전은 [system-flow.html](system-flow.html) |
| [docs/roadmap.md](roadmap.md) | 해커톤 MVP 범위와 해커톤 이후 추가할 것 |

## 함께 일하는 규칙

| 문서 | 읽는 사람 | 내용 |
|---|---|---|
| [AGENTS.md](../AGENTS.md) | AI 에이전트·사람 | 영역 지도, 계약 파일, 충돌 잦은 파일, 작업 범위, 검증 명령 |
| [CLAUDE.md](../CLAUDE.md) | Claude Code | AGENTS.md를 불러오고 Claude 전용 규칙만 추가 |
| 폴더별 `AGENTS.md` | AI 에이전트 | [backend](../backend/AGENTS.md) · [security_engine](../security_engine/AGENTS.md) · [frontend](../frontend/AGENTS.md) · [mcp-handoff](../integrations/mcp-handoff/AGENTS.md) · [deploy](../deploy/AGENTS.md) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 사람 | 이슈 → 브랜치 → 커밋 → PR 흐름, 이름 규칙, 자동 검사 |
| [.github/CODEOWNERS](../.github/CODEOWNERS) | GitHub | 영역별 리뷰어 자동 지정 |

## 제출·발표

| 문서 | 내용 |
|---|---|
| [docs/submission/](submission/README.md) | 제출까지 실행 계획, 발표 자료·시연 영상·쇼츠 초안, 사실 확인 목록 |
| [docs/external-resources.md](external-resources.md) | 외부 자원 활용 내역. **빠지면 실격**, 제출 양식으로 옮길 원본 |
| [docs/competitors.md](competitors.md) | 핵심 경쟁사 4곳과 우리 차별점 |
| [docs/competitors2.md](competitors2.md) | 경쟁사와 권한·로컬 검사·알림 비교 (설계 기준) |

## 기능별 설명

| 영역 | 문서 | 내용 |
|---|---|---|
| 보안엔진 | [security_engine/README.md](../security_engine/README.md) | 스캐너 설치, 실행, 출력 JSON 규격, 규칙 추가 |
| GPU LLM 해석 | [docs/llm.md](llm.md) | 문맥 분석, SSVC 위험도, OS별 대응 가이드, Blue–Red, 모델·서버 |
| 비동기 해석 | [docs/async-llm.md](async-llm.md) | DB 큐와 worker, 인증, 활성화 절차 (기본 꺼짐) |
| 리포트·신고서 | [docs/reports.md](reports.md) | 비전공자용 점검·완료 리포트, KISA 24시간·72시간 신고서 초안 |
| MCP 전달 | [integrations/mcp-handoff/README.md](../integrations/mcp-handoff/README.md) | 수정 지시를 AI 코딩툴에 넘기는 MCP 서버 |
| 프론트 | [frontend/README.md](../frontend/README.md) | 대시보드 실행 방법, 예제 데이터 범위 |
| DB | [docs/db-erd.md](db-erd.md), [docs/db-schema.sql](db-schema.sql), [docs/migrations/](migrations/) | ERD, 스키마, 적용 SQL |
| 검사 결과 저장 | [docs/scan-persistence.md](scan-persistence.md) | `scan_job` 저장과 적용 절차 |
| 서버 배포 | [deploy/general-server/README.md](../deploy/general-server/README.md) | 일반 서버 systemd·Caddy·GPU 터널 구성 |
| 프론트 인수인계 | [deploy/general-server/FRONTEND_HANDOFF.md](../deploy/general-server/FRONTEND_HANDOFF.md) | 서버 기준 API 상태와 프론트 연결 방법 |

## 문서 쓰는 규칙

- 결정된 것과 제안을 구분합니다. 팀이 정하지 않은 값은 "결정 필요"로 남깁니다.
- 기준 날짜를 적습니다. 구현 상태가 바뀌면 문서도 같은 PR에서 고칩니다.
- 설계 문서(system-flow, competitors2)는 "설계 기준"이고, 구현 상태는 roadmap과 각 기능 문서가 기준입니다. 발표 자료에서 둘을 섞지 않습니다.
