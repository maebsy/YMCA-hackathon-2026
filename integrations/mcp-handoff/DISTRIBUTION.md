# 72hours MCP 연결·배포 안내

설치 없이 원격으로 쓰는 서비스 MCP입니다. AI에게 "이 저장소 점검해 줘"라고 하면 서버의 72hours(검사 → GPU 해석 → 수정 지시 → 재검사 → 리포트)를 그대로 씁니다.

- 주소(고정): `https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc`
- 방식: Streamable HTTP, JSON 응답. 인증 없음(공개 데모).
- 로그인·소유권 확인은 하지 않습니다(웹과 같음). 검사할 수 있는 저장소는 서버의 허용 소유자 목록(#69)을 따릅니다.

## 클라이언트별 연결

| 클라이언트 | 연결 방법 |
|---|---|
| Claude Code | `claude mcp add --transport http 72hours-service https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc` |
| Codex CLI | `codex mcp add 72hours-service --url https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc` |
| Cursor | `https://oboe-handiness-enroll.ngrok-free.dev/mcp/service`의 설치 버튼 (deeplink) |
| VS Code | 같은 페이지의 설치 버튼, 또는 `code --add-mcp '{"name":"72hours-service","type":"http","url":"https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc"}'` |
| Claude 웹·데스크톱 | 설정 → 커넥터 → 사용자 지정 커넥터 추가 → 위 주소, 인증 없음 |
| 그 밖의 원격 HTTP MCP 클라이언트 | 설정 파일: `https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/config.json` |

연결 뒤 `service_info`를 불러 도구가 보이는지 확인합니다. 등록 화면에서 "성공"이라고만 나와도 실제 도구 목록(`tools/list`)이 보이기 전에는 연결된 것이 아닙니다.

## 쓰는 법 (한 번에)

1. **점검**: "72hours로 https://github.com/<소유자>/<저장소> 점검해 줘" → AI가 `audit_repository`를 한 번 부릅니다.
   - 검사(최대 90초 대기)
   - 위험도 상위 항목 GPU 해석 자동 시작
   - 요약과 다음 할 일
2. **수정 지시 받기**: `audit_status`로 해석이 끝난 항목을 확인하고 `get_fix_prompt`로 받습니다(Red 통과한 것만).
3. **고치고 확인**
   - 사용자가 허락한 항목만 AI가 로컬에서 고칩니다.
   - push 후 `check_fix`로 재검사해서 해결 / 계속 / 새로 / 키 재발급 필요를 확인합니다.
4. **실행으로 증명**: `verify_demo`는 격리 샌드박스에서 "수정 전 공격 성공 → 수정 후 차단 + 기능 테스트 통과"를 실행으로 보여 줍니다. **지금은 데모 과녁 전용**입니다.
5. 미리 만든 명령(MCP prompts): `security_audit`, `fix_and_verify`

## 공식 MCP Registry 등록 (운영자)

`registry/server.json`은 원격 전용 서버 형식입니다(`remotes`, 패키지 없음). 이름 `io.github.maebsy/72hours`는 GitHub 계정 `maebsy`로 인증해야 등록됩니다. 그래서 **저장소 소유자가 직접** 진행합니다.

```bash
# mcp-publisher 설치: https://github.com/modelcontextprotocol/registry/releases (OS에 맞는 파일)
cd integrations/mcp-handoff/registry
mcp-publisher login github      # 브라우저에서 maebsy 계정으로 승인
mcp-publisher publish           # server.json 등록
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.maebsy/72hours"
```

- 레지스트리는 이름(네임스페이스)만 확인하고 원격 주소의 소유는 확인하지 않습니다. 그래서 주소는 **바뀌지 않는 고정 주소**여야 합니다.
- 버전을 올릴 때는 `version`을 바꿔 다시 `publish` 합니다.

## 그 밖의 목록 사이트

공식 레지스트리를 읽어 가는 클라이언트·목록이 늘고 있습니다. 개별 등록이 필요한 곳(예: mcp.so, Smithery, Glama, PulseMCP)은 각 사이트에서 계정으로 제출해야 합니다. 제출 문구는 위 "쓰는 법"과 주소를 그대로 씁니다.

## 한계 (사실대로)

- 공개 GitHub 저장소만, 서버 허용 소유자 목록 안에서만 검사합니다.
- ngrok 무료 요금제: 월 HTTP 요청 2만 건, 데이터 전송 1GB. 넘으면 그달에는 고정 주소가 막힙니다.
- `verify_demo`는 데모 과녁만 실행합니다. 사용자 저장소의 실행 증명은 아직 없습니다.
- 재검사는 기본 브랜치에 push 된 커밋만 봅니다(로컬 수정·PR 브랜치는 못 봄).
