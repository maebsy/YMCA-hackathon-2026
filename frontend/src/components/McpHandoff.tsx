"use client";

// 웹 검사 결과를 MCP 서버(integrations/mcp-handoff)로 넘기는 칸.
// 검사가 끝나면 page.tsx 가 마지막 결과를 브라우저에 저장(saveLast)하므로, 여기서는 그 값을 읽어
// MCP 서버가 받는 JSON 파일과 저장소·커밋이 채워진 클라이언트 설정을 만듭니다.
import React, { useMemo, useSyncExternalStore } from "react";
import { Download, Copy } from "lucide-react";
import { loadLast } from "@/lib/api";
import { BLOCK_LABEL, buildHandoff, clientConfig } from "@/lib/mcp";
import type { OS } from "@/types/security";

interface Props {
  os: OS;
  onShowToast: (msg: string) => void;
}

// 다른 탭에서 저장한 결과도 반영합니다. 같은 탭의 새 검사는 부모가 다시 그릴 때 getSnapshot 으로 읽힙니다
const subscribe = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
};
// 문자열로 비교해야 값이 같을 때 다시 그리지 않습니다 (loadLast 는 매번 새 객체를 돌려줌)
const readLast = () => JSON.stringify(loadLast() ?? null);
// 서버 렌더링(정적 빌드)에는 브라우저 저장소가 없습니다
const readNothing = () => "__server__";

export const McpHandoff: React.FC<Props> = ({ os, onShowToast }) => {
  const raw = useSyncExternalStore(subscribe, readLast, readNothing);
  const handoff = useMemo(
    () => (raw === "__server__" ? { ok: false as const, why: "검사 결과를 불러오는 중..." } : buildHandoff(JSON.parse(raw))),
    [raw],
  );

  const download = () => {
    if (!handoff.ok) return;
    const blob = new Blob([JSON.stringify(handoff.snapshot, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = handoff.fileName;
    a.click();
    URL.revokeObjectURL(url);
    onShowToast(`MCP용 결과 파일을 저장했습니다: ${handoff.fileName}`);
  };

  const copyConfig = async () => {
    if (!handoff.ok) return;
    try {
      await navigator.clipboard.writeText(clientConfig(handoff, os));
      onShowToast("MCP 클라이언트 설정을 복사했습니다. 경로의 <사용자>와 설치 위치를 바꿔 붙여 넣으세요.");
    } catch {
      onShowToast("복사에 실패했습니다. 클립보드 권한을 확인해 주세요.");
    }
  };

  return (
    <div className="pt-3 border-t border-[#27272a] space-y-2" data-testid="mcp-handoff">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-[#a1a1aa]">
          {handoff.ok ? (
            <>
              검사 대상 <code>{handoff.repository}</code>@<code>{handoff.revision.slice(0, 7)}</code> · 전달 가능{" "}
              <b className="text-[#d4ff3a]">{handoff.ready}건</b>
              {handoff.blocked.length > 0 && (
                <>
                  {" "}
                  · 차단 {handoff.blocked.map((b) => `${BLOCK_LABEL[b.reason]} ${b.count}`).join(", ")}
                </>
              )}
            </>
          ) : (
            handoff.why
          )}
        </span>
        <div className="flex gap-2">
          <button
            onClick={download}
            disabled={!handoff.ok}
            className="px-3 py-1.5 rounded border border-[#d4ff3a]/60 text-[#d4ff3a] font-mono text-[11px] font-bold hover:bg-[#d4ff3a]/10 transition flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" /> MCP용 결과 내려받기
          </button>
          <button
            onClick={copyConfig}
            disabled={!handoff.ok}
            className="px-3 py-1.5 rounded border border-[#27272a] text-[#fafafa] font-mono text-[11px] font-bold hover:border-[#d4ff3a]/60 transition flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <Copy className="w-3.5 h-3.5" /> MCP 설정 복사
          </button>
        </div>
      </div>
      <p className="font-mono text-[11px] text-[#71717a] leading-relaxed">
        파일을 저장하고 설정을 AI 코딩툴(Cursor·Claude Code)의 MCP 설정에 붙여 넣은 뒤 다시 시작하면, 에이전트가{" "}
        <code>list_findings</code>로 목록을 보고 <code>get_fix_prompt</code>로 Red 검증을 통과한 수정 지시만 받습니다.
      </p>
    </div>
  );
};
