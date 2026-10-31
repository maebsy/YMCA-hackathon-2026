<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# frontend 작업 규칙 (팀)

위 블록은 `next dev`가 자동으로 넣는 부분이니 그대로 둡니다. 팀 규칙은 이 아래에만 씁니다.
루트 [AGENTS.md](../AGENTS.md)를 먼저 읽습니다. 담당: 조은익 `@nick19850906-debug` (보조 박기태 `@SeouliteParker`).

## 구조

| 경로 | 하는 일 |
|---|---|
| `src/app/page.tsx` | 첫 화면과 탭 전환 |
| `src/components/tabs/` | 작업 공간·리포트·사고 대응·구조 설명 탭 (파일마다 250~620줄) |
| `src/components/McpHandoff.tsx`, `src/lib/mcp.ts` | 검사 결과를 MCP로 AI 코딩툴에 넘기는 화면 |
| `src/lib/api.ts` | 백엔드 호출 모음 (`/api/scans`, `/api/llm/*`, `/api/reports/plain`) |
| `src/types/security.ts` | 백엔드 응답 타입. `backend/app/llm/schemas.py`와 맞춥니다 |
| `src/data/mockData.ts` | 화면 예제 데이터 |

## 지킬 것

- **백엔드 호출은 `src/lib/api.ts`에 모읍니다.** 상대 경로 `/api/...`만 씁니다. Next.js 서버가 `BACKEND_ORIGIN`으로 프록시합니다(`next.config.ts`).
- 브라우저에 공개되는 `NEXT_PUBLIC_*` 변수를 쓰지 않습니다. GPU 서버 주소·API 키를 화면 코드에 넣지 않습니다.
- **예제 데이터를 실제 결과처럼 보이게 하지 않습니다.** 지금처럼 "예제"라고 표시합니다(#40). 발표 화면에서 심사위원이 실제 기능으로 오해하면 안 됩니다.
- **화면 문구에 코드에 없는 기능이나 확인 안 된 숫자를 쓰지 않습니다.** 엔진 이름·규칙 수·처리 시간처럼 사실 확인이 필요한 문구는 해당 영역 담당자에게 확인받습니다.
- MCP 도구 이름(`list_findings`, `get_fix_prompt`, `fix_finding`)은 `integrations/mcp-handoff/server.py`와 같아야 합니다.
- 탭 파일이 큽니다. 포맷만 바뀌는 diff를 만들지 않고, 새 기능은 새 컴포넌트 파일로 만들어 불러옵니다.
- `package-lock.json`은 손으로 고치지 않습니다. 패키지를 추가하면 `docs/external-resources.md`도 같은 PR에서 고칩니다.

## 실행과 검증

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000, 백엔드는 127.0.0.1:8000
npm run lint
npm run build
```
