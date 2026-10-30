# 72hours MCP 결과 전달

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

## 사용자 에이전트에 연결

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
- 읽기 전용 로컬 stdio만 지원합니다. 파일 내용은 연결한 AI 클라이언트에 전달되므로 클라우드 모델을 쓰는 호스트에서는 외부로 전달될 수 있습니다. 결과 파일 접근 권한은 운영자가 관리합니다.

## 이후 서비스 연동 시 필요한 작업

현재 범위는 파일 기반 전달입니다. 실시간 대시보드/DB 조회나 다중 사용자 원격 MCP는 구현하지 않았습니다. 그 단계에서는 기존 인증 경계 안에서 사용자·프로젝트별 읽기 전용 조회, 검사 대상 커밋·scan ID의 서버 측 결합, 최신 상태 및 재검사 이력 확인을 먼저 추가해야 합니다. 지금 서버를 그대로 공개 HTTP 서비스로 노출하면 안 됩니다.

새 검사 결과에는 사용자 저장소·검사 커밋·검사 시각을 상위 시스템에서 함께 기록하는 것이 좋습니다. 이 PR은 그 계약을 강제로 바꾸지 않고 운영자 인자로 연결합니다. 외부 자원은 저장소 규칙에 따라 `docs/external-resources.md`에 기록합니다.
