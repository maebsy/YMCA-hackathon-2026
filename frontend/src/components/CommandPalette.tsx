"use client";

import React, { useState } from "react";
import { TabType } from "@/types/security";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRepo: (repoUrl: string) => void;
  onSwitchTab: (tab: TabType) => void;
  onToggleTheme: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onSelectRepo,
  onSwitchTab,
  onToggleTheme,
}) => {
  const [search, setSearch] = useState("");

  if (!isOpen) return null;

  const items = [
    {
      id: "repo-cafe",
      label: "[저장소 스캔] minji-cafe/order-site (Next.js + Supabase)",
      action: () => {
        onSwitchTab("workspace");
        onSelectRepo("https://github.com/minji-cafe/order-site");
        onClose();
      },
      tag: "Enter ⏎",
      highlight: true,
    },
    {
      id: "repo-vibe",
      label: "[저장소 스캔] vibe-coder/ai-saas-starter (Express + Prisma)",
      action: () => {
        onSwitchTab("workspace");
        onSelectRepo("https://github.com/vibe-coder/ai-saas-starter");
        onClose();
      },
      tag: "Enter ⏎",
      highlight: true,
    },
    {
      id: "tab-report",
      label: "[화면 이동] ⑤ 72시간 완료 리포트 & OWASP ZAP 재현 보기",
      action: () => {
        onSwitchTab("report");
        onClose();
      },
      tag: "View",
      highlight: false,
    },
    {
      id: "tab-incident",
      label: "[화면 이동] 24시간(KISA) · 72시간(개보위) 사고 신고서 초안 작성",
      action: () => {
        onSwitchTab("incident");
        onClose();
      },
      tag: "View",
      highlight: false,
    },
    {
      id: "tab-architecture",
      label: "[화면 이동] 시스템 아키텍처 & Red-Blue 검증 루프",
      action: () => {
        onSwitchTab("architecture");
        onClose();
      },
      tag: "View",
      highlight: false,
    },
    {
      id: "toggle-theme",
      label: "[테마 전환] 다크 모드(#0a0a0a) ↔ 라이트 모드(#fafafa) 토글",
      action: () => {
        onToggleTheme();
        onClose();
      },
      tag: "Theme",
      highlight: false,
    },
  ];

  const filteredItems = items.filter((item) =>
    item.label.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-start justify-center pt-24 p-4">
      <div className="w-full max-w-xl bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden shadow-2xl">
        <div className="p-3.5 border-b border-[#27272a] flex items-center gap-3">
          <span className="font-mono text-sm text-[#d4ff3a]">$</span>
          <input
            type="text"
            placeholder="명령어 입력 또는 데모 저장소 선택... (ESC로 닫기)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            className="flex-1 bg-transparent font-mono text-sm text-white focus:outline-none placeholder:text-[#a1a1aa]"
          />
          <kbd
            onClick={onClose}
            className="px-1.5 py-0.5 text-[10px] font-mono bg-[#18181b] text-[#a1a1aa] rounded border border-[#27272a] cursor-pointer"
          >
            ESC
          </kbd>
        </div>

        <div className="p-2 max-h-80 overflow-y-auto divide-y divide-[#27272a]/50 font-mono text-xs">
          {filteredItems.map((item) => (
            <button
              key={item.id}
              onClick={item.action}
              className="w-full text-left p-3 rounded hover:bg-[#18181b] flex items-center justify-between cursor-pointer transition"
            >
              <span className={item.highlight ? "text-[#d4ff3a]" : "text-white"}>
                {item.label}
              </span>
              <span className="text-[#a1a1aa]">{item.tag}</span>
            </button>
          ))}
          {filteredItems.length === 0 && (
            <div className="p-4 text-center text-[#a1a1aa]">
              일치하는 명령어가 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
