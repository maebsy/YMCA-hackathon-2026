# 별도 원격 MCP 배포

기존 웹/백엔드/GPU 프로세스와 별도의 Python 가상환경 및 systemd 사용자 서비스로 실행합니다.
프론트 담당 PR #66의 다운로드 UI는 수정하지 않습니다. 연결 페이지는 MCP 프로세스가 제공합니다.

1. 최신 검토한 `integrations/mcp-handoff/` 코드를 `~/apps/72hours/mcp/current/`에 배치합니다.
2. `python3.12 -m venv ~/apps/72hours/mcp/.venv` 후 그 Python으로 `pip install -r current/requirements.txt`.
3. **공개를 허용한** 최소 결과 JSON만 `~/apps/72hours/mcp/results.json`에 600 권한으로 저장합니다.
4. `~/.config/72hours/mcp.env`를 600 권한으로 만듭니다. 값은 실제 검사 대상 저장소/SHA입니다.

```dotenv
MCP_REPOSITORY=owner/repo
MCP_REVISION=검사한_40자리_SHA
MCP_PUBLIC_ORIGIN=https://현재-공개호스트
```

5. `systemd/72hours-mcp.service`를 `~/.config/systemd/user/`에 복사하고
   `systemctl --user daemon-reload && systemctl --user enable --now 72hours-mcp`.
6. `http://127.0.0.1:8765/mcp/health`와 실제 MCP initialize/tools 호출을 확인합니다.
7. Caddy 2.11+의 기존 관리 설정에 대해 `python3 enable-remote-mcp.py`를 실행합니다.
   후보 설정 검증·백업 후 SIGUSR1 재적용, 웹/API/MCP 상태와 기존 PID를 확인합니다.
   검증 실패 시 설정을 복구합니다. 기존 접근 정책과 터널 프로세스는 유지합니다.
8. 외부 HTTPS `/mcp/connect`, `/mcp/agent.txt`, `/mcp`의 실제 통신을 확인합니다.

연결 시 사용자의 PC에는 Python·VPN·SSH 키가 필요하지 않습니다. AI 호스트 자신의
MCP 등록 권한/승인은 필요하며 모든 호스트가 자연어만으로 등록할 수 있는 것은 아닙니다.

변경된 결과를 공개하려면 대상 저장소/SHA를 다시 확인하고 MCP 서비스만 재시작합니다.
다른 사용자의 결과를 자동으로 포함하지 않습니다. 공개 허용 결과가 아닌 데이터는 별도 인증과
프로젝트 권한 경계를 구현하기 전에는 배포하지 않습니다. 현재 공개 샘플은 NodeGoat 결과입니다.

롤백: 기록된 `Caddyfile.quick.before-mcp-*` 중 이번 적용의 백업을 복원하고
Caddy에 SIGUSR1을 보낸 뒤 `systemctl --user stop 72hours-mcp`.
다른 배포가 프록시를 바꾼 뒤에는 파일 전체를 복원하지 말고 MCP 블록만 제거합니다.

Quick Tunnel은 임시 주소입니다. 운영용 고정 도메인/터널로 전환할 때 MCP_PUBLIC_ORIGIN과
클라이언트 주소를 함께 갱신합니다. SSE 대신 stateless JSON 응답을 사용합니다.

참고: [MCP SDK](https://py.sdk.modelcontextprotocol.io/v1/server/),
[Quick Tunnel 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
