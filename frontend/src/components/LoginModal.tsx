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
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden shadow-2xl">
        <div className="chrome-bar justify-between">
          <div className="flex items-center gap-2">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              72hours.app/login
            </span>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-xs text-[#a1a1aa] hover:text-white cursor-pointer flex items-center gap-1"
          >
            <X className="w-3.5 h-3.5" /> ESC
          </button>
        </div>

        <div className="p-8 text-center flex flex-col items-center gap-5">
          <div className="font-mono text-3xl font-bold">
            72<span className="text-[#d4ff3a]">hours</span>_
          </div>
          <p className="text-sm text-[#a1a1aa]">
            찾고, 고치고, 72시간 안에 끝냅니다.
          </p>

          <div className="w-full space-y-2.5 pt-2">
            <button
              onClick={() => onSelectProvider("GitHub")}
              className="w-full py-3 px-4 rounded-lg bg-[#d4ff3a] text-[#0a0a0a] font-mono text-sm font-bold hover:brightness-110 transition flex items-center justify-center gap-2 cursor-pointer"
            >
              <GithubIcon className="w-4 h-4" /> GitHub로 계속하기
            </button>
            <button
              onClick={() => onSelectProvider("Google")}
              className="w-full py-3 px-4 rounded-lg bg-[#18181b] text-white border border-[#27272a] font-mono text-sm hover:bg-[#27272a] transition flex items-center justify-center gap-2 cursor-pointer"
            >
              <span className="font-bold">G</span> Google로 계속하기
            </button>
          </div>

          <span className="font-mono text-[11px] text-[#a1a1aa] leading-relaxed">
            로그인하면 저장소를 읽기 전용으로만 봅니다 · 코드는 검사 후 즉시 지웁니다
            <br />
            <code className="text-[#d4ff3a]">
              Authorization: Bearer &lt;supabase_access_token&gt;
            </code>{" "}
            (#32)
          </span>
        </div>
      </div>
    </div>
  );
};
