// 홈의 "AI 코딩 도구에 연결" 안내. 이름과 도메인은 여기 한 곳에서만 바꿉니다.
// 이름은 사용자 클라이언트에 붙는 별칭(가안)입니다. 서버 안내문(/mcp/service/agent.txt)은 지금 72hours-service를 씁니다.
export const MCP_SERVER_NAME = "72hour_mcp";
// 서버의 MCP_PUBLIC_ORIGIN 대표 주소와 같아야 합니다. 빌드 때 NEXT_PUBLIC_MCP_ORIGIN으로 바꿀 수 있습니다.
export const MCP_ORIGIN = (process.env.NEXT_PUBLIC_MCP_ORIGIN?.trim() || "https://oboe-handiness-enroll.ngrok-free.dev").replace(/\/+$/, "");
export const MCP_ENDPOINT = `${MCP_ORIGIN}/mcp/service/rpc`;

export type McpTarget = {
  id: string; label: string;
  /** cli: 터미널 한 줄, prompt: 아무 AI 에이전트 채팅에 붙여 넣는 영어 지시문 */
  kind: "cli" | "prompt";
  text: string;
};

// Codex·Claude Code는 공식 명령(2026-11-01 확인). 그 밖의 에이전트는 자연어 지시로 각자 방식에 맞게 추가하게 합니다.
export function mcpTargets(name = MCP_SERVER_NAME, url = MCP_ENDPOINT): McpTarget[] {
  return [
    { id: "claude", label: "Claude Code", kind: "cli", text: `claude mcp add --transport http ${name} ${url}` },
    { id: "codex", label: "Codex", kind: "cli", text: `codex mcp add ${name} --url ${url}` },
    { id: "prompt", label: "Prompt", kind: "prompt", text:
      `Add a remote MCP server named "${name}" to this agent. ` +
      `URL: ${url} . Transport: Streamable HTTP. No authentication, API key or custom headers are needed. ` +
      `Use this agent's own way of adding MCP servers (CLI command or config file), then verify the connection by calling the server's service_info tool.` },
  ];
}
