# 사실 확인 목록

발표 자료·README·화면 문구·영상 자막에 쓰기 전에 이 표에서 확인합니다. 심사위원은 저장소를 열어 보고, 상위 팀은 라이브 시연과 질의응답을 합니다. **코드에 없는 것을 있다고 말하면 질문 하나에 무너집니다.**

기준: 2026-10-31 17:00 main(`2de3a09`)과 열린 브랜치.

- ✅ 구현됨, 그대로 써도 됨
- ⚠️ 구현됐지만 표현을 조심해야 함
- ❌ 구현 안 됨. "계획", "다음 단계"로만 씀

## 1. 기능 주장

| 주장 | 판정 | 근거 | 쓸 때 표현 |
|---|---|---|---|
| 스캐너 3종(Opengrep·OSV-Scanner·Gitleaks)과 자체 설정 검사기로 찾음 | ✅ | `security_engine/runners/`, [README](../../security_engine/README.md) | 그대로 |
| 우리 바이브코딩 규칙 21개 | ✅ | `rules/vibe-coding.yml` 19개 + `rules/vibe-coding-config.yml` 2개 | 발표 직전에 다시 세기 |
| Aikido 규칙(MIT)도 사용 | ❌ | main 코드에 Aikido 규칙 파일·설정 없음. 문구는 `feat/frontend-live-sync-ux`의 README·`ArchitectureTab.tsx`·`mockData.ts`에만 있음 | 규칙을 실제로 넣고 외부 자원 표에 적거나, 문구를 지움 |
| 재검사 때 새로 생김·계속 있음·해결됨·확인 불가로 비교 | ✅ | `security_engine/compare.py` | 그대로 |
| SSVC·KEV·EPSS로 위험도 판정, 판정은 코드가 함 | ✅ | `backend/app/llm/risk.py`, `intel.py`, [llm.md](../llm.md) | 그대로 |
| OS별 대응 명령은 템플릿에서만 나옴(LLM이 지어내지 않음) | ✅ | `backend/app/llm/remediation.py` | 그대로 |
| GPU LLM(Qwen3.8-27B 4비트, L4 24GB)이 Blue 설명을 쓰고 Red가 공격자 관점으로 검증 | ✅ | `backend/app/llm/pipeline.py`, [llm.md](../llm.md) | 그대로 |
| Red 검증을 통과한 수정만 전달 | ⚠️ | 최대 2회 재시도 후에도 실패하면 버리지 않고 "수동 확인 필요"로 표시해 전달 | "통과 못 한 것은 '수동 확인 필요'로 따로 표시" |
| 수정 지시를 MCP로 Cursor·Claude Code 같은 AI 코딩툴에 전달 | ⚠️ | main에는 로컬 stdio MCP(`integrations/mcp-handoff`). 설치 없는 원격 연결은 #76 머지 후 | 시연하는 방식 기준으로 말하기 |
| 비전공자용 점검·완료 리포트 | ✅ | `POST /api/reports/plain`, [reports.md](../reports.md) | 그대로 |
| KISA 침해사고 24시간·개인정보 유출 72시간 신고서 초안 | ✅ | `POST /api/reports/incident-24h`, `/privacy-72h` | "초안 작성 지원", 최종 판단·제출은 사업자 |
| 72시간 타이머 | ⚠️ | 화면(`frontend/src/app/page.tsx`)이 첫 발견 시각으로 계산. 서버 관리 타이머·알림은 [roadmap](../roadmap.md)의 추가 항목 | "화면에서 첫 발견부터 남은 시간을 보여 줌" |
| 매일 새 CVE와 대조해 알림 | ❌ | roadmap 3장: 지금은 재검사 버튼으로 수동 | "다음 단계" |
| GitHub App 연결, 비공개 저장소 | ❌ | roadmap 1·3장: 지금은 공개 저장소 주소만 | "다음 단계" |
| 허니토큰으로 유출 즉시 탐지 | ❌ | 기획안(골든타임 72)에만 있음. 코드 없음 | "다음 단계" |
| Google·GitHub 로그인 | ⚠️ | 서버 쪽 인증은 #60 진행 중. 화면 로그인은 예제(`page.tsx`의 안내 문구) | 시연에서 보여 주지 않거나 "준비 중" |
| 검사 대상은 허용한 소유자의 저장소만 | ⚠️ | #69 머지 후에 참 | 머지 여부 확인 후 |

## 2. 데이터·보안 주장

| 주장 | 판정 | 근거 | 쓸 때 표현 |
|---|---|---|---|
| 받은 소스는 검사 후 삭제 | ✅ | `security_engine/git.py`가 임시 폴더에 clone, `engine.py`가 검사 뒤 삭제 | 그대로 |
| 원본 소스를 전혀 남기지 않음(Zero-Retention) | ⚠️ | 소스 전체는 지우지만, 결과 JSON에 문제 줄 주변 코드가 들어가고 DB `scan_job`에 저장됨([scan-persistence.md](../scan-persistence.md)) | "소스 전체는 지우고, 결과와 문제 줄 일부만 저장" |
| 코드가 외부 AI로 나가지 않음 | ✅ | LLM은 우리 GPU 서버의 vLLM. 단 OSV.dev에는 패키지 이름·버전, KEV·EPSS에는 CVE 번호를 조회함 | "코드는 외부 AI에 보내지 않음. 취약점 DB 조회에는 패키지 이름·버전만" |
| 비밀값은 가려서 저장 | ✅ | `security_engine/llm_input.py` `_redact`, README 4장 | 그대로 |
| 사용자 코드를 실행하지 않음 | ✅ | roadmap 1장 "코드는 실행하지 않고 읽기만" | 그대로 |

## 3. 숫자

| 숫자 | 상태 | 할 일 |
|---|---|---|
| 기획안의 시장·사고 통계(바이브코딩 앱 RLS 꺼짐 약 70%, 노출 기록 18,697건, 키 노출 60% 이상, e나무 유출 등) | 기획안에 출처는 있으나 원문 링크 미확인 | 발표 자료에 쓰는 숫자만 원문을 열어 확인하고 출처를 장표에 적음 |
| 개인정보 유출 72시간 통지·신고 의무, 미신고 과태료 | 기획안: 개인정보보호법 제34조·시행령 제40조 | 법 조문 원문 확인. 2026 개정법 시행일은 기획안에도 "확인 필요" |
| GPU 효과(이해도·조치 성공률) | 아직 측정 안 함 | [gpu-evaluation.md](gpu-evaluation.md) 실험 후에만 씀 |
| 처리 시간(검사·해석) | 아직 정리 안 함 | 시연 저장소로 실제 측정한 값만 씀 |
| 화면 성능 문구(예: 120fps) | 측정 근거 없음 | 발표에 쓰지 않음 |
