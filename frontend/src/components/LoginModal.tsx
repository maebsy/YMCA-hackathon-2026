"use client";

import React from "react";
import { X } from "lucide-react";
import { GithubIcon } from "@/components/icons/GithubIcon";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectProvider: (provider: string) => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({
  isOpen,
  onClose,
  onSelectProvider,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-[var(--paper-solid)] border-2 border-[var(--ink-line)] rounded-[34px_14px_38px_16px] overflow-hidden shadow-2xl ink-card-interactive">
        <svg className="card-corner-ink" viewBox="0 0 200 200">
          <use href="#ink-bleed-motif" />
        </svg>
        <div className="relative z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--ink-line)]">
          <div className="flex items-center gap-2.5">
            <span className="seal-mark small">印</span>
            <span className="font-mono text-xs text-[var(--ink-jung)] font-bold">
              72hours.app/login · 소유자 인증
            </span>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-xs text-[var(--ink-jung)] hover:text-[var(--ink-nong)] cursor-pointer flex items-center gap-1"
          >
            <X className="w-4 h-4" /> ESC
          </button>
        </div>

        <div className="relative z-10 p-8 text-center flex flex-col items-center gap-5">
          <div className="font-serif-kr text-3xl font-black text-[var(--ink-nong)]">
            72<span className="text-[var(--jade-deep)]">hours</span> · 潑墨
          </div>
          <p className="text-sm text-[var(--ink-jung)]">
            찾고, 고치고, 72시간 안에 끝냅니다.
          </p>

          <div className="w-full space-y-2.5 pt-2">
            <button
              onClick={() => onSelectProvider("GitHub")}
              className="w-full py-3.5 px-4 rounded-[20px_6px_20px_6px] bg-[var(--ink-nong)] text-[var(--paper-bg)] font-mono text-sm font-bold hover:bg-[var(--jade-deep)] transition flex items-center justify-center gap-2 cursor-pointer"
            >
              <GithubIcon className="w-4 h-4" /> GitHub로 계속하기 (읽기 전용)
            </button>
            <button
              onClick={() => onSelectProvider("Google")}
              className="w-full py-3.5 px-4 rounded-[20px_6px_20px_6px] bg-[var(--paper-bg)] text-[var(--ink-nong)] border border-[var(--ink-line)] font-mono text-sm font-bold hover:border-[var(--ink-nong)] transition flex items-center justify-center gap-2 cursor-pointer"
            >
              <span className="font-bold text-[var(--juhong-seal)]">G</span> Google로 계속하기
            </button>
          </div>

          <span className="font-mono text-[11px] text-[var(--ink-dam)] leading-relaxed">
            로그인하면 저장소를 읽기 전용으로만 봅니다 · 코드는 검사 후 즉시 지웁니다
            <br />
            <code className="text-[var(--jade-deep)] font-bold">
              Authorization: Bearer &lt;supabase_access_token&gt;
            </code>{" "}
            (#32)
          </span>
        </div>
      </div>
    </div>
  );
};
