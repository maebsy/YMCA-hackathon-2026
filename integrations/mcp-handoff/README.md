# 72hours MCP — AI 대화로 서비스 이용

운영 중인 서비스의 `/mcp/service`에서 서버 URL을 복사해 Claude의 custom connector,
ChatGPT의 custom MCP server 또는 기타 AI의 원격 MCP 설정에 등록합니다. 현재 데모 인증은 None입니다.
Cursor·VS Code는 같은 화면의 연결 버튼도 사용할 수 있습니다. 등록 후 `service_info` 호출로 연결을 확인합니다.
웹 채팅은 저장소 URL로 서비스를 이용하며, 직접 코드 수정은 파일 접근 권한이 있는 코딩 에이전트에서 수행합니다.
원격 주소는 `/mcp/service/rpc`, 에이전트용 안내는 `/mcp/service/agent.txt`입니다.
Python·CMD·결과 파일 설치 없이 원격 HTTP MCP를 지원하는 클라이언트에서 사용합니다.
클라이언트 자체의 연결 승인·재접속은 필요할 수 있으며, stdio 전용 앱은 별도 브리지가 필요합니다.

`create_workspace → start_scan → get_scan → start_analysis → get_analysis → get_fix_prompt`
순으로 실제 서버 API를 호출합니다. 수정은 사용자 AI의 작업본에서 수행합니다.
`rescan`은 같은 저장소의 **게시된 기본 브랜치**를 이전 결과와 비교합니다. 미게시 로컬 수정이나
PR 브랜치를 확인하지 못하므로 커밋이 같으면 수정 검증 완료로 표시하면 안 됩니다.
`generate_report`와 `incident_report`는 기존 서비스의 점검 리포트·사고 평가·신고서 초안을
제공합니다. 신고 자동 제출·계정 관리·과금·임의 셸 실행·배포 도구는 제공하지 않습니다.

기존 `/mcp/connect`는 웹에서 이미 검사한 결과의 전용 연결 기능으로 유지됩니다.
전체 서비스 MCP는 브라우저 결과를 신뢰하거나 업로드받지 않고, **자기가 접수한 서버 작업**의
실제 저장소·커밋·FindingInput을 연결합니다. GPU 키는 전달받지 않습니다.

운영 실행은 기존 `live_server.py --database /absolute/private/links.sqlite3 --public-origin https://HOST`
명령을 사용합니다. 같은 디렉터리의 `workspaces.sqlite3`에 만료 시간·capability 해시·접수 ID만
보관하며, 원본 코드·분석 전문·비밀키는 저장하지 않습니다. backend는 고정 loopback `127.0.0.1:8000`을
호출하고 기존 인증·allowlist·queue 정책을 그대로 따릅니다. 인증이 필요한 환경에서는 정책 오류를
반환하며 우회하지 않습니다. 이 구성은 인증 없는 공개 데모 API가 이미 허용된 배포용입니다.

capability는 24시간, 작업 공간은 최대 128개, 전체 접수 256건, 공간별 16건입니다
(`WorkspaceStore` 운영 설정). 같은 scan request_id 및 같은 분석 입력은 중복 접수하지 않습니다.
응답이 불명확한 POST는 `not_confirmed`로 남겨 자동 재접수를 막습니다. 서버가 접수했을 가능성이
있으므로 운영자가 확인하기 전 새 request_id로 무작정 반복하지 마세요.
폐기는 MCP 접근을 제거하며 이미 백엔드에 접수된 작업을 취소하지는 않습니다.
DB를 유지한 프로세스 재시작 후에도 ID가 유지되지만, backend 결과 보관 기간이 지나면 새 검사가 필요합니다.

검증: `python -m unittest discover -s integrations/mcp-handoff/tests -v`.
HTTP MCP 초기화·전체 API 계약·두 작업 공간 격리·동시 중복 요청·만료/폐기·인증/오류·Red 게이트를
합성 테스트로 확인하고, 배포 후 공개 HTTPS에서 실제 검사→GPU 분석→리포트→재검사를 별도 확인합니다.

---

# 기존 로컬 결과 전달 모드

기존 서비스 옆에서 별도 프로세스로 실행하는 읽기 전용 MCP 서버입니다. 로컬 LLM이 이미 만든 `ai_fix_prompt`에 저장소 확인·최소 수정·테스트·재검사 지침을 붙여 사용자 AI 코딩 에이전트에 제공합니다. 백엔드를 import하지 않고 API·DB·GPU·compose·서비스 의존성을 바꾸지 않습니다.

```text
기존 로컬 LLM → 결과 JSON 저장 → 이 MCP 서버 (stdio)
                                    ↑ 사용자 AI 에이전트가 조회
                                    ↓ 수정 제안 + 실제 검증 지침
                              사용자 저장소에서 수정·테스트·재검사
```

MCP가 사용자 에이전트에 먼저 push하거나 자동으로 수정시키지는 않습니다. 사용자가 MCP를 연결하고 작업을 요청하면 에이전트가 tool을 호출합니다. [공식 SDK 문서](https://py.sdk.modelcontextprotocol.io/v1/)의 tools와 prompts를 제공하며, 지원 클라이언트의 사용자 메뉴에서는 `fix_finding` prompt를 직접 선택할 수도 있습니다. SDK v1 유지보수 API를 사용하며 `mcp==1.30.0`으로 고정했습니다.

## 설치 및 확인

저장소 루트에서 PowerShell로 실행합니다. 기존 `backend/.venv`에 설치하지 않습니다.

```powershell
python -m venv integrations/mcp-handoff/.venv
integrations/mcp-handoff/.venv/Scripts/python.exe -m pip install -r integrations/mcp-handoff/requirements.txt
integrations/mcp-handoff/.venv/Scripts/python.exe -m unittest discover -s integrations/mcp-handoff/tests -v
```

macOS/Linux에서는 `.venv/Scripts/python.exe`를 `.venv/bin/python`으로 바꿉니다. 테스트는 GPU·네트워크·서비스 실행 없이 합성 결과와 실제 stdio 클라이언트로 수행합니다. 차단된 prompt 요청의 오류 로그는 의도한 거부 경로입니다.

## 결과 연결

입력은 진행 중인 #16의 다음 두 출력 계약을 지원합니다. 해당 기능이 main에 머지되지 않아도 MCP 자체 설치와 합성 데이터 테스트는 독립적으로 가능합니다.

| 입력 | 구조 | 실행 인자 |
|---|---|---|
| `/api/llm/explain` 응답을 저장한 JSON | `{"mode":"red_blue","results":[...]}` | `--results` |
| `python -m app.llm.check`가 저장한 JSON | `{"model":"...","runs":[{"mode":"red_blue","results":[...]}]}` | `--results`와 **명시적 `--run-index`** |

`--run-index`는 0부터 시작합니다. Blue와 Red–Blue가 둘 다 있는 실측 보고서는 실제 `runs`를 확인해서 선택하세요. 가장 최신 파일이나 이전 pass 결과를 자동 선택하지 않습니다. 한 번에 1~50건, 파일 최대 2 MiB입니다. 운영자가 지정한 파일만 시작 시 한 번 읽고 메모리에 필요한 필드만 보관하므로 새 결과를 연결하려면 MCP 프로세스를 재시작해야 합니다. 파일 작성 완료 후 연결하세요.

```powershell
integrations/mcp-handoff/.venv/Scripts/python.exe integrations/mcp-handoff/server.py `
  --results C:/private/scan-results.json `
  --repository owner/scanned-app `
  --revision <검사한_사용자_저장소의_40자리_SHA>
```

`repository`와 `revision`은 **72hours 서비스 저장소가 아니라 검사 대상 사용자 저장소**입니다. 현재 상위 출력에는 이 정보가 없어 운영자가 지정합니다. MCP가 이 연결 관계나 파일의 진위를 인증하지는 않습니다. LLM 실측 fixture는 실제 사용자 저장소의 검사 결과가 아니므로 운영 결과로 연결하지 마세요.

직접 실행하면 입력을 기다리는 것이 정상입니다. stdout은 MCP JSON-RPC 전용입니다. 일반적으로 클라이언트가 서버 프로세스를 실행하게 합니다.

## 웹 자동 저장으로 최신 결과 읽기 (#65)

웹(대시보드)에서 검사하면 결과 파일을 자동으로 덮어쓰고, MCP는 **`--revision` 없이** 실행해 호출할 때마다 최신 파일을 읽습니다. 재검사로 커밋이 바뀌어도 설정을 고치거나 MCP를 재시작할 필요가 없습니다.

1. 웹 "④ MCP 연동" 칸에서 **자동 저장 켜기**를 눌러 결과 파일(`72hours-mcp-<owner>-<repo>.json`) 위치를 한 번 고릅니다. 이후 검사·해석이 끝날 때마다 같은 파일에 저장됩니다(크롬·엣지). 다른 브라우저는 **MCP용 결과 내려받기**로 같은 파일 이름에 저장합니다.
2. **MCP 설정 복사**로 받은 설정을 최초 한 번만 클라이언트에 붙여 넣습니다. 형식은 아래와 같습니다.

```text
server.py --results <결과 파일 절대 경로> --repository <owner/repo>
```

`--repository`는 생략할 수 있지만 **함께 주는 것을 권장합니다.** 생략하면 그 경로에 어떤 저장소의 결과 파일이 저장돼도 그대로 전달합니다. 웹의 설정 복사는 항상 `--repository`를 넣습니다.

| 동작 | 내용 |
|---|---|
| 최신 결과 | 호출할 때 파일 내용(sha256)이 바뀌었으면 다시 읽습니다. 같은 시각·같은 크기로 덮어써도 반영됩니다 |
| 저장소·커밋 | 파일 안의 `source.repository`·`source.revision`·`source.generated_at`을 씁니다. `list_findings`의 `source`에 나옵니다 |
| 저장소 고정 | `--repository`와 파일의 저장소가 다르면 그 파일은 받지 않고 직전 결과를 유지합니다 |
| 깨진 파일 | 저장 도중·형식 오류면 직전 정상 결과를 유지하고 `notice`로 알립니다 |
| 파일 없음 | 서버는 뜨고 `list_findings`가 빈 목록과 "자동 저장을 켜 주세요" 안내를 돌려줍니다 |
| 파일 삭제 | 한 번 읽은 뒤 파일이 사라지면 직전 결과를 유지하고 `notice`로 알립니다 |

`--revision`을 주면 기존처럼 시작할 때 한 번 읽는 고정 방식입니다. 이때 파일의 `source.revision`이 다르면 거부합니다.

## 사용자 에이전트에 연결

### 실제 웹 검사 연결 (#71)

`live_server.py` 배포에서는 `/mcp/connect`가 같은 브라우저의 실제 검사 결과를 읽습니다.
사용자가 확인 후 전용 연결을 만들고, **수정 요청 복사** 문장을 자기 AI 에이전트에게 전달합니다.
파일 설치 없이 해당 검사에만 연결하며 24시간 만료와 직접 폐기를 지원합니다.
공용 샘플은 자동 대체하지 않습니다. 브라우저 export임을 명시하고 에이전트가 저장소·커밋·코드 근거를 확인합니다.
자세한 데이터 경계·배포·검증은 [실제 검사 MCP 안내](../../deploy/general-server/live-mcp.md)를 참고하세요.

### 설치 없는 원격 연결 (#68)

공개 허용된 결과를 운영자가 `http_server.py`로 배포하면 사용자는 ZIP/Python 설치 없이
`https://<공개호스트>/mcp/connect`의 문장을 AI 에이전트에게 전달합니다.
에이전트는 `/mcp/agent.txt`를 읽고 호스트의 지원 방식으로 `/mcp`를 등록합니다.
호스트가 설정 수정 권한을 주지 않으면 사용자가 MCP 추가 화면에서 URL을 등록해야 합니다.
실행 권한·연결 승인이나 클라이언트 재접속을 우회하지 않습니다.

- 표준 Streamable HTTP, stateless JSON 응답: Quick Tunnel이 지원하지 않는 SSE에 의존하지 않습니다.
- Claude Code, Codex, Cursor, VS Code 및 원격 HTTP 지원 호스트용 안내를 제공합니다.
- 기존 `list_findings`, `get_fix_prompt`, `fix_finding`의 전달 조건은 동일합니다.
- 127.0.0.1에만 바인딩하고 명시한 공개 Host/Origin만 허용하며 본문은 64 KiB로 제한합니다.
- 인증 없는 공개 고정 스냅샷 전용입니다. **개인 검사 파일을 이 엔드포인트에 올리면 안 됩니다.**
  배포 시 `--publish-approved-snapshot`으로 공개 허용을 명시해야 합니다.
- 새 웹 검사 자동 조회·개인 프로젝트·스캔 시작·업로드는 지원하지 않습니다. 다중 사용자
  서비스 연동에는 사용자/프로젝트 권한과 결과 ID 연결을 별도로 구현해야 합니다.

일반 서버 배포는 [원격 MCP 배포 안내](../../deploy/general-server/remote-mcp.md)를 따릅니다.
실제 공개 결과는 저장소에 커밋하지 않습니다. 테스트는 합성 결과만 사용합니다.

### 로컬 stdio 연결 (기존 방식)

`client.example.json`은 `mcpServers` 형식을 사용하는 클라이언트용 Windows 설정 예시입니다. 실행 파일·서버 파일·결과 파일 경로를 **모두 절대 경로**로 바꾸고 검사 대상 저장소와 커밋을 입력하세요. 실측 보고서는 args에 `"--run-index", "0"` 등을 추가합니다. 이 파일은 자동 적용되지 않으며 기존 클라이언트 설정이나 실행 중인 Claude 세션을 변경하지 않습니다. 다른 설정 형식의 호스트에서도 같은 command와 args를 등록하면 됩니다.

연결한 뒤 사용자 에이전트에 요청할 문장:

> 72hours-handoff의 list_findings로 현재 연결된 검사 결과를 확인해 줘. ready=true인 항목의 get_fix_prompt를 가져오고, 대상 저장소와 검사 커밋이 현재 작업 대상인지 확인해 줘. 기존 변경을 보존하면서 관련 취약점만 수정하고, 정상 기능 테스트와 보안 재검사 결과를 알려 줘. 차단된 항목은 임의로 수정하지 말고 확인이 필요한 이유를 알려 줘.

| MCP 기능 | 입력 | 출력 |
|---|---|---|
| tool `list_findings` | 없음 | 저장소·커밋·파일 SHA-256·run index, fingerprint별 ready와 차단 이유 |
| tool `get_fix_prompt` | `fingerprint` | 제안과 검증 지침을 포함한 텍스트; 차단·미존재 항목은 tool error |
| prompt `fix_finding` | `fingerprint` | 같은 내용을 user 메시지로 제공; 같은 차단 규칙 적용 |

## 전달 조건과 경계

- `status=done`, `variant=D`, `red_verdict=pass`, 마지막 `red_rounds`의 판정도 pass이며 issues가 비어 있어야 합니다.
- `needs_manual_review=false`, `false_positive_suspect=false`가 **명시적 boolean**이어야 합니다. 누락·문자열·실패·오탐 의심 결과의 수정 지시는 전달하지 않습니다.
- fingerprint 일치, 비어 있지 않은 ai_fix_prompt, 모델과 프롬프트 버전을 확인합니다. 중복 fingerprint·중복 JSON 키는 거부합니다.
- 소스 코드 조각, context, 모델의 원본 오류, 공격 시나리오는 전달하지 않습니다. 허용 필드만 사용하고 알려진 키 패턴을 다시 가립니다. 임의 형식의 비밀값까지 완전하게 탐지하지는 못하므로 생산 단계에서도 비밀값과 코드 원문을 제거해야 합니다.
- 프롬프트의 LLM 결과는 이스케이프한 JSON 데이터입니다. 이는 주입 방어의 한 층이지 모델이 악성 제안을 절대 따르지 않는다는 보장은 아닙니다. 수신 에이전트가 사용자 권한·코드 근거·작업 범위를 확인해야 합니다.
- **Red pass는 LLM의 제안 검토이며 실제 공격 실행, 코드 수정 성공, 취약점 해결 확인이 아닙니다.** 완료 판정은 사용자 측 테스트와 원래 탐지기의 재검사가 필요합니다.
- 기본 실행은 읽기 전용 로컬 stdio입니다. 별도 `http_server.py`는 공개 허용된 고정 스냅샷만 원격으로 제공합니다. 파일 내용은 연결한 AI 클라이언트에 전달되므로 클라우드 모델을 쓰는 호스트에서는 외부로 전달될 수 있습니다. 결과 파일 접근 권한은 운영자가 관리합니다.

## 이후 서비스 연동 시 필요한 작업

현재 범위는 파일 기반 전달입니다. 실시간 대시보드/DB 조회나 다중 사용자 원격 MCP는 구현하지 않았습니다. 그 단계에서는 기존 인증 경계 안에서 사용자·프로젝트별 읽기 전용 조회, 검사 대상 커밋·scan ID의 서버 측 결합, 최신 상태 및 재검사 이력 확인을 먼저 추가해야 합니다. 지금 서버를 그대로 공개 HTTP 서비스로 노출하면 안 됩니다.

새 검사 결과에는 사용자 저장소·검사 커밋·검사 시각을 상위 시스템에서 함께 기록하는 것이 좋습니다. 이 PR은 그 계약을 강제로 바꾸지 않고 운영자 인자로 연결합니다. 외부 자원은 저장소 규칙에 따라 `docs/external-resources.md`에 기록합니다.
