# 대화에서 사용하는 전체 서비스 MCP (#75)

웹: `/mcp/service` — 연결 문장 복사, Cursor·VS Code 설치 링크, 선택적 JSON 설정 다운로드.
AI 안내: `/mcp/service/agent.txt`. 원격 MCP: `/mcp/service/rpc` (Streamable HTTP, stateless JSON).
기존 `/mcp/connect`와 검사별 `/mcp/h/...`는 유지합니다.

기존 Caddy `/mcp/* → 127.0.0.1:8765` 경로와 `72hours-mcp-live.service`를 그대로 사용합니다.
`live_server.py`가 결과 전달 서버와 전체 서비스 MCP의 세션 매니저를 함께 시작합니다.
MCP만 재시작하며 backend/frontend/GPU/tunnel을 변경하지 않습니다.

1. 별도 release 디렉터리에 `integrations/mcp-handoff`의 Python 파일과 web 디렉터리를 복사합니다.
2. 독립 venv에 해당 `requirements.txt`를 설치합니다. backend 의존성은 변경하지 않습니다.
3. 후보를 다른 포트(예:8766)에서 실행하여 `/mcp/service/health`와 MCP initialize/tools/list를 확인합니다.
4. 기존 live-current 경로·systemd unit을 백업하고 심볼릭 링크만 후보 release로 교체합니다.
5. MCP unit만 재시작하고 `/`, `/api/health`, `/api/llm/health`, 기존 MCP 및 새 경로를 확인합니다.
6. 실패 시 이전 링크/unit으로 복원합니다. 기존 네 서비스의 PID가 유지되는지 확인합니다.

작업 데이터는 `--database` 옆 `workspaces.sqlite3`입니다. 전용 디렉터리 권한700, unit UMask0077,
DB600을 유지하고 access log를 끕니다. DB에는 workspace 토큰 해시·만료·접수 메타데이터만 저장합니다.
원문 토큰은 호출자의 AI 대화에 남으므로 공유·로그·커밋하지 마세요. 만료는24시간입니다.
별도 계정 인증을 대신하는 설계가 아니라, 이미 공개된 데모 API 위에서 작업별 결과를 분리하는 capability입니다.
정식 다중 사용자 서비스는 기존 계정별 backend 인증을 연결한 후 공개 운영해야 합니다.

백엔드 주소는 operator 고정 `http://127.0.0.1:8000`입니다. 사용자가 임의 URL/헤더를 지정할 수 없고,
backend401/403은 그대로 실패합니다. GPU API key·SSH key·서버 관리자 자격은 MCP에 넣지 않습니다.
POST는 무작정 재시도하지 않습니다. 불명확한 접수는 `not_confirmed`이며 운영자가 확인해야 합니다.
MCP 재시작은 진행 중인 backend 작업을 취소하지 않고, 재시작 후 동일 capability/ID로 조회합니다.

## 2026-10-31 실제 검증

- 공개 HTTPS에서 MCP initialize, tools/list(11개), create_workspace, start_scan 호출.
- 대상 OWASP/NodeGoat, 커밋 `c5cb68a7084e4ae7dcc60e6a98768720a81841e8`.
- 실제 엔진 scan `74d55abd97a34939a827a1cb1242bc51`: 4개 엔진 성공, 탐지212건, LLM 입력 묶음28건.
- 실제 GPU `qwen3.8-27b` / prompt `2026-10-31.6` 분석 완료; 선택 항목 Red 통과 후 수정 프롬프트 반환.
- 리포트: 분석 완료1건, 미완료0건, 실제 보안 점검 리포트 생성.
- 재검사 `753cc33e4bbc44008133bc6d86300961`: 동일 커밋, 신규0/지속212/해결0.
  코드를 게시하지 않았으므로 해결로 표시하지 않는 것이 정상입니다.
- 자동 테스트40개: 기존 stdio/live-file/scoped HTTP, 전체 API 흐름, 격리, 만료/폐기,
  동시 중복 접수, 응답 불확실, backend 인증 거부, 잘못된 대상, Red 전달 차단.

클라이언트 앱마다 승인·재연결 방식은 다릅니다. 공식 설치 링크 규격과 웹 복사를 확인했으며,
모든 데스크톱 클라이언트의 설치 UI를 각각 실행한 것은 아닙니다.
