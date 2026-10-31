"use client";

import { Terminal, Cpu, ShieldAlert, FileCheck2, Sun, Moon } from "lucide-react";
import { GithubIcon } from "@/components/icons/GithubIcon";
import { TabType } from "@/types/security";

interface HeaderProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  onOpenCmdPalette: () => void;
  onOpenLoginModal: () => void;
  authUser: string;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onTabChange,
  onOpenCmdPalette,
  onOpenLoginModal,
  authUser,
  theme,
  onToggleTheme,
}) => {
  return (
    <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#0a0a0a]/80 border-b border-[#27272a]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <a
            href="#"
            className="font-mono text-xl font-bold tracking-tight flex items-center gap-1 text-white"
          >
            72<span className="text-[#d4ff3a]">hours</span>
            <span className="animate-pulse text-[#d4ff3a]">_</span>
          </a>
          <div className="hidden lg:flex items-center gap-2 px-3 py-1 rounded-full bg-[#111113] border border-[#27272a] font-mono text-xs text-[#a1a1aa]">
            <span className="w-2 h-2 rounded-full bg-[#d4ff3a] animate-ping" />
            <span className="w-2 h-2 rounded-full bg-[#d4ff3a] -ml-3" />
            <span>GPU LLM (vLLM · L4) : ONLINE</span>
            <span className="text-[#27272a]">|</span>
            <span className="text-[#fafafa]">Red–Blue Loop v1.4</span>
          </div>
        </div>

        {/* 메인 뷰 전환 탭 */}
        <nav className="hidden md:flex items-center gap-1 bg-[#111113] p-1 rounded-lg border border-[#27272a] font-mono text-xs shrink-0">
          <button
            onClick={() => onTabChange("workspace")}
            className={`nav-btn px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
              activeTab === "workspace"
                ? "active bg-[#d4ff3a] text-black font-bold"
                : "text-[#a1a1aa] hover:text-white"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>워크스페이스</span>
          </button>
          <button
            onClick={() => onTabChange("architecture")}
            className={`nav-btn px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
              activeTab === "architecture"
                ? "active bg-[#d4ff3a] text-black font-bold"
                : "text-[#a1a1aa] hover:text-white"
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>시스템 & Red-Blue</span>
          </button>
          <button
            onClick={() => onTabChange("incident")}
            className={`nav-btn px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
              activeTab === "incident"
                ? "active bg-[#d4ff3a] text-black font-bold"
                : "text-[#a1a1aa] hover:text-white"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>24h·72h 신고 서포트</span>
          </button>
          <button
            onClick={() => onTabChange("report")}
            className={`nav-btn px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
              activeTab === "report"
                ? "active bg-[#d4ff3a] text-black font-bold"
                : "text-[#a1a1aa] hover:text-white"
            }`}
          >
            <FileCheck2 className="w-3.5 h-3.5" />
            <span>완료 리포트 & API</span>
          </button>
        </nav>

        {/* 우측 유틸리티 버튼 */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <button
            onClick={onToggleTheme}
            className="p-2 rounded-md bg-[#111113] hover:bg-[#18181b] border border-[#27272a] text-[#a1a1aa] hover:text-white transition cursor-pointer"
            title="다크/라이트 테마 전환"
          >
            {theme === "dark" ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={onOpenCmdPalette}
            className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-[#111113] hover:bg-[#18181b] border border-[#27272a] font-mono text-xs text-[#a1a1aa] transition cursor-pointer whitespace-nowrap"
          >
            <span>빠른 스캔</span>
            <kbd className="px-1.5 py-0.5 text-[10px] bg-[#18181b] text-[#fafafa] rounded border border-[#27272a]">
              ⌘K
            </kbd>
          </button>

          <button
            onClick={onOpenLoginModal}
            className="px-3.5 py-1.5 rounded-md bg-[#d4ff3a] text-[#0a0a0a] font-mono text-xs font-bold hover:brightness-110 transition flex items-center gap-1.5 cursor-pointer shrink-0 whitespace-nowrap"
          >
            <GithubIcon size={14} className="w-3.5 h-3.5" />
            <span>{authUser}</span>
          </button>
        </div>
      </div>
      <nav aria-label="모바일 탭" className="md:hidden px-4 pb-3">
        <select
          aria-label="화면 선택"
          value={activeTab}
          onChange={(e) => onTabChange(e.target.value as TabType)}
          className="w-full rounded-lg border border-[#27272a] bg-[#111113] p-2 font-mono text-sm text-white"
        >
          <option value="workspace">워크스페이스</option>
          <option value="architecture">시스템 & Red-Blue</option>
          <option value="incident">24h·72h 신고 서포트</option>
          <option value="report">완료 리포트 & API</option>
        </select>
      </nav>
    </header>
  );
};
