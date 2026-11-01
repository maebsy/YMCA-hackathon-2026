"use client";

import { useState } from "react";
import { Check, Copy, Unplug } from "lucide-react";
import { mcpTargets } from "@/lib/mcp-connect";
import "./mcp-connect.css";

/** Home: pick an AI coding agent, then copy one command or config to add the 72hours remote MCP. */
export default function McpConnect({ embedded = false }: { embedded?: boolean }) {
  const targets = mcpTargets();
  const [active, setActive] = useState(targets[0].id);
  const [copied, setCopied] = useState("");
  const [status, setStatus] = useState("");
  const target = targets.find(item => item.id === active) ?? targets[0];
  function choose(id: string) { setActive(id); setCopied(""); setStatus(""); }
  async function copy() {
    try { await navigator.clipboard.writeText(target.text); setCopied(target.id); setStatus(target.kind === "cli" ? `${target.label} 명령을 복사했습니다.` : "지시문을 복사했습니다. 사용하는 AI 에이전트 채팅에 붙여 넣으세요."); }
    catch { setCopied(""); setStatus("복사하지 못했습니다. 내용을 직접 선택해 복사해 주세요."); }
  }
  return <section className={embedded ? "mc mc-embedded" : "card mc"} aria-labelledby="mcp-connect-title">
    <h2 id="mcp-connect-title"><Unplug size={17} aria-hidden="true"/>AI 코딩 도구에서 쓰기</h2>
    <p className="mc-hint">한 줄만 붙여 넣으면 점검부터 수정까지 쓰던 도구 안에서 이어집니다.</p>
    <div className="mc-agents" role="group" aria-label="AI 코딩 도구">
      {targets.map(item => <button key={item.id} type="button" aria-pressed={item.id === target.id}
        className={item.id === target.id ? "mc-agent mc-agent-on" : "mc-agent"} onClick={() => choose(item.id)}>{item.label}</button>)}
    </div>
    <p className="mc-where">{target.kind === "cli" ? "터미널에서 실행" : ""}</p>
    <div className={`mc-box mc-${target.kind}`}>
      <pre className="mc-text" tabIndex={0} aria-label={target.kind === "cli" ? `${target.label} 연결 명령` : "에이전트용 연결 지시문"}>{target.text}</pre>
      <button type="button" className="mc-copy" aria-label={target.kind === "cli" ? `${target.label} 명령 복사` : "지시문 복사"} onClick={() => void copy()}>
        {copied === target.id ? <Check size={14} aria-hidden="true"/> : <Copy size={14} aria-hidden="true"/>}
      </button>
    </div>
    <p className="mc-status" role="status" aria-live="polite">{status}</p>
  </section>;
}
