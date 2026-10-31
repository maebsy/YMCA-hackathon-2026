"use client";

import React from "react";
import { CheckCircle2 } from "lucide-react";

interface ToastProps {
  message: string;
  visible: boolean;
}

export const Toast: React.FC<ToastProps> = ({ message, visible }) => {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 px-5 py-3.5 rounded-[20px_6px_20px_6px] bg-[var(--ink-nong)] text-[var(--paper-bg)] border border-[var(--jade-deep)] font-mono text-xs font-bold shadow-2xl transition-all duration-300 flex items-center gap-2.5 pointer-events-none ${
        visible ? "translate-y-0 opacity-100" : "translate-y-20 opacity-0"
      }`}
    >
      <CheckCircle2 className="w-4 h-4 shrink-0 text-[#4CA692]" />
      <span>{message}</span>
    </div>
  );
};
