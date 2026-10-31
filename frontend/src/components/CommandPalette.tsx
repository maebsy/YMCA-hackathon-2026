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

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth" });
  };

  const items = [
    {
      id: "repo-cafe",
      label: "[저장소 스캔] minji-cafe/order-site (Next.js + Supabase)",
      action: () => {
        onSwitchTab("workspace");
        scrollToSection("sim-sec");
        onSelectRepo("https://github.com/minji-cafe/order-site");
        onClose();
      },
      tag: "Enter ⏎",
      highlight: true,
    },
    {
      id: "repo-ymca",
      label: "[저장소 스캔] maebsy/YMCA-hackathon-2026 (현재 깃 저장소)",
      action: () => {
        onSwitchTab("workspace");
        scrollToSection("sim-sec");
        onSelectRepo("https://github.com/maebsy/YMCA-hackathon-2026");
        onClose();
      },
      tag: "Enter ⏎",
      highlight: true,
    },
    {
      id: "sec-flow",
      label: "[화면 이동] 一 여백 속을 흐르는 5단계 보안 점검 흐름",
      action: () => {
        scrollToSection("flow-sec");
        onClose();
      },
      tag: "一 절차",
      highlight: false,
    },
    {
      id: "sec-eval",
      label: "[화면 이동] 三 GPU & Red–Blue 효과 평가 설계 보드",
      action: () => {
        onSwitchTab("architecture");
        scrollToSection("eval-sec");
        onClose();
      },
      tag: "三 평가",
      highlight: false,
    },
    {
      id: "sec-report",
      label: "[화면 이동] 四 24h(KISA)·72h(개보위) 신고 서포트 & 완료 리포트",
      action: () => {
        onSwitchTab("report");
        scrollToSection("report-sec");
        onClose();
      },
      tag: "四 보고",
      highlight: false,
    },
    {
      id: "toggle-theme",
      label: "[농담 전환] 화선지 주간(晝 #F5F2EB) ↔ 묵향 야간(夜 #141618) 전환",
      action: () => {
        onToggleTheme();
        onClose();
      },
      tag: "晝/夜",
      highlight: false,
    },
  ];

  const filteredItems = items.filter((item) =>
    item.label.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-24 p-4">
      <div className="w-full max-w-xl bg-[var(--paper-solid)] border-2 border-[var(--ink-line)] rounded-[28px_10px_30px_12px] overflow-hidden shadow-2xl">
        <div className="p-4 border-b border-[var(--ink-line)] flex items-center gap-3">
          <span className="seal-mark small">尋</span>
          <input
            type="text"
            placeholder="명령어 입력 또는 검사할 저장소 선택... (ESC로 닫기)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            className="flex-1 bg-transparent font-mono text-sm text-[var(--ink-nong)] focus:outline-none placeholder:text-[var(--ink-dam)]"
          />
          <kbd
            onClick={onClose}
            className="px-2 py-0.5 text-[11px] font-mono bg-[var(--paper-bg)] text-[var(--ink-jung)] rounded border border-[var(--ink-line)] cursor-pointer"
          >
            ESC
          </kbd>
        </div>

        <div className="p-2 max-h-80 overflow-y-auto divide-y divide-[var(--ink-line)] font-mono text-xs">
          {filteredItems.map((item) => (
            <button
              key={item.id}
              onClick={item.action}
              className="w-full text-left p-3.5 rounded-xl hover:bg-[var(--jade-soft)] flex items-center justify-between cursor-pointer transition"
            >
              <span
                className={
                  item.highlight
                    ? "text-[var(--jade-deep)] font-bold"
                    : "text-[var(--ink-nong)]"
                }
              >
                {item.label}
              </span>
              <span className="text-[var(--ink-dam)]">{item.tag}</span>
            </button>
          ))}
          {filteredItems.length === 0 && (
            <div className="p-4 text-center text-[var(--ink-dam)]">
              일치하는 명령어가 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
