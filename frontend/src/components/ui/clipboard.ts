"use client";
import { useRef, useState } from "react";

export function useClipboard() {
  const [feedback, setFeedback] = useState("");
  const operation = useRef(0);
  function clearFeedback() { operation.current++; setFeedback(""); }
  async function copy(text: string) {
    const current = ++operation.current;
    setFeedback("");
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      if (current === operation.current) setFeedback("클립보드에 복사했습니다.");
    } catch {
      if (current === operation.current) setFeedback("복사하지 못했습니다. 텍스트를 직접 선택해 복사해 주세요.");
    }
  }
  return { feedback, copy, clearFeedback };
}
