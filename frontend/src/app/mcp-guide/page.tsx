import type { Metadata } from "next";
import McpConnect from "@/components/mcp-connect";

export const metadata: Metadata = { title: "MCP로 전달 — 72hours", description: "검사 결과와 수정 지시를 Cursor·Claude Code 같은 AI 코딩 도구로 바로 보냅니다." };

// 핵심 기능 카테고리(실검증 · MCP로 전달 · 사고 신고) 중 MCP 전용 화면. 연결 카드는 홈과 같은 컴포넌트입니다
export default function Page() {
  return <main id="main" className="workspace container" tabIndex={-1}>
    <div className="workspace-heading">
      <p className="eyebrow">MCP · AI CODING TOOLS</p>
      <h1>쓰던 AI 코딩 도구에서 바로 고칩니다.</h1>
      <p>72hours를 MCP로 연결하면 Cursor·Claude Code·Codex 안에서 &ldquo;이 저장소 점검해 줘&rdquo; 한마디로 검사 → 수정 지시 → 재검사 → 실제검증까지 이어집니다. 아래에서 도구를 고르고 한 줄을 붙여 넣으세요.</p>
    </div>
    <McpConnect/>
    <ol className="mcp-steps">
      <li><strong>연결</strong> 도구를 고르고 명령(또는 지시문)을 한 번 붙여 넣습니다.</li>
      <li><strong>점검</strong> AI에게 &ldquo;이 저장소 점검해 줘&rdquo;라고 말하면 72hours가 검사하고 위험한 항목부터 알려 줍니다.</li>
      <li><strong>수정·확인</strong> Red 검증을 통과한 수정 지시만 받아 고치고, 다시 검사해 해결 여부를 확인합니다.</li>
    </ol>
  </main>;
}
