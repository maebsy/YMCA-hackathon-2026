# mcp-handoff 작업 규칙

루트 [AGENTS.md](../../AGENTS.md)를 먼저 읽습니다. 담당: 유영민 `@maebsy` (보조 박기태 `@SeouliteParker`). 자세한 설명은 [README.md](README.md)에 있습니다.

## 지킬 것

- **독립 프로세스입니다.** `backend/`를 import하지 않고, 백엔드·DB·GPU·compose 설정을 바꾸지 않습니다.
- **전용 venv**(`integrations/mcp-handoff/.venv`)를 씁니다. `backend/.venv`에 설치하지 않습니다.
- MCP SDK 버전은 `requirements.txt`에 고정돼 있습니다. 올리려면 담당자와 먼저 이야기합니다.
- **도구 이름이 계약입니다.** `list_findings`, `get_fix_prompt`, `fix_finding`을 바꾸면 프론트(`frontend/src/lib/mcp.ts`, `McpHandoff.tsx`, `WorkspaceTab.tsx`)가 깨집니다. #63이 실제로 이 문제였습니다.
- MCP는 읽기 전용입니다. 사용자 에이전트에 먼저 push하거나 자동으로 수정시키지 않습니다.
- 2026-10-31 현재 이 폴더를 크게 바꾸는 PR(#70·#74·#76)이 열려 있습니다. 그 PR들이 정리되기 전에는 다른 사람이 이 폴더를 고치지 않습니다.

## 테스트

```bash
python -m venv integrations/mcp-handoff/.venv
integrations/mcp-handoff/.venv/Scripts/python.exe -m pip install -r integrations/mcp-handoff/requirements.txt
integrations/mcp-handoff/.venv/Scripts/python.exe -m unittest discover -s integrations/mcp-handoff/tests -v
```

macOS·Linux에서는 `.venv/Scripts/python.exe` 대신 `.venv/bin/python`을 씁니다. 테스트는 GPU·네트워크 없이 합성 데이터로 돕니다.
