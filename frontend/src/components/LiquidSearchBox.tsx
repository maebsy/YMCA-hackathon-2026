"use client";

import React, { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import { Search, Sparkles, RotateCcw, HelpCircle } from "lucide-react";

export interface LiquidSearchBoxHandle {
  playAnimation: (durationMs?: number, onDone?: () => void) => void;
}

interface LiquidSearchBoxProps {
  repoInput: string;
  onChangeRepoInput: (val: string) => void;
  onTriggerScan: () => void;
  mode?: "intro" | "hero";
  onCloseIntro?: () => void;
}

const getMinimalStageText = (pct: number) => {
  if (pct < 25) return "① 소스·패키지 추출 중";
  if (pct < 55) return "② 4대 보안 엔진 스캔 중";
  if (pct < 85) return "③ 로컬 GPU Red–Blue 검증 중";
  if (pct < 100) return "④ MCP 수정 프롬프트 생성 중";
  return "✓ 100% 스마트 스캔 완료";
};

export const LiquidSearchBox = forwardRef<
  LiquidSearchBoxHandle,
  LiquidSearchBoxProps
>(
  (
    {
      repoInput,
      onChangeRepoInput,
      onTriggerScan,
      mode = "hero",
      onCloseIntro,
    },
    ref
  ) => {
    // 120fps 고프레임 직접 DOM 제어용 Ref (React 리렌더링 0회로 끊김 원천 제거)
    const fillLayerRef = useRef<HTMLDivElement | null>(null);
    const syncFillRef = useRef<HTMLDivElement | null>(null);
    const countTextRef = useRef<HTMLSpanElement | null>(null);
    const pillBadgeRef = useRef<HTMLSpanElement | null>(null);
    const stageTextRef = useRef<HTMLSpanElement | null>(null);
    const btnTextRef = useRef<HTMLSpanElement | null>(null);
    const stepRefs = useRef<(HTMLDivElement | null)[]>([]);
    const rafIdRef = useRef<number | null>(null);

    const applyFrameDOM = (floatPct: number, isRunning: boolean) => {
      const clampedFloat = Math.max(0, Math.min(100, floatPct));
      const intPct = Math.round(clampedFloat);
      const widthStr = `${clampedFloat.toFixed(2)}%`;

      if (fillLayerRef.current) {
        fillLayerRef.current.style.width = widthStr;
      }
      if (syncFillRef.current) {
        syncFillRef.current.style.width = widthStr;
      }
      if (countTextRef.current) {
        countTextRef.current.textContent = `${intPct}%`;
      }
      if (pillBadgeRef.current) {
        pillBadgeRef.current.textContent = `${intPct}%`;
      }
      if (stageTextRef.current) {
        stageTextRef.current.textContent = getMinimalStageText(intPct);
      }
      if (btnTextRef.current) {
        btnTextRef.current.textContent = isRunning
          ? `스캔 ${intPct}%`
          : "물결 스캔";
      }

      const thresholds = [25, 55, 85, 100];
      thresholds.forEach((t, idx) => {
        const el = stepRefs.current[idx];
        if (!el) return;
        if (intPct >= t) {
          el.setAttribute("data-active", "true");
        } else {
          el.setAttribute("data-active", "false");
        }
      });
    };

    const playAnimation = (durationMs = 1900, onDone?: () => void) => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      const start = performance.now();

      const tick = (now: number) => {
        const elapsed = now - start;
        const progress = Math.min(1, elapsed / durationMs);
        // 부드러운 사인/큐빅 혼합 곡선 (초당 60~144프레임 서브픽셀 보간)
        const eased = 1 - Math.pow(1 - progress, 2.2);
        const currentPct = eased * 100;

        applyFrameDOM(currentPct, progress < 1);

        if (progress < 1) {
          rafIdRef.current = requestAnimationFrame(tick);
        } else {
          applyFrameDOM(100, false);
          if (onDone) onDone();
        }
      };

      rafIdRef.current = requestAnimationFrame(tick);
    };

    useImperativeHandle(ref, () => ({
      playAnimation,
    }));

    useEffect(() => {
      applyFrameDOM(100, false);
      return () => {
        if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      };
    }, []);

    return (
      <div className="liquid-search-shell">
        {/* 미니멀 상단 컨트롤 줄 + 툴팁 */}
        <div className="flex items-center justify-between gap-2 mb-2.5 px-1">
          <div className="inline-flex items-center gap-1.5 text-xs font-bold text-[#0284C7]">
            <span className="w-2 h-2 rounded-full bg-gradient-to-r from-[#38BDF8] to-[#2DD4BF]" />
            <span>SMART AQUA SCAN</span>
            {/* 툴팁 아이콘 */}
            <div className="group relative inline-flex items-center">
              <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-[#0284C7] cursor-help" />
              <div className="SmartTooltip">
                저장소 스캔 시 검색창 왼쪽(0%)부터 오른쪽(100%)으로 물결이 차오르며
                하단 카운트업과 1:1로 동기화됩니다.
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => playAnimation(1900)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white border border-sky-200 text-[11.5px] font-bold text-[#0284C7] hover:bg-sky-50 transition cursor-pointer"
            >
              <RotateCcw className="w-3 h-3" />
              <span>0%→100% 리플레이</span>
            </button>
            {mode === "intro" && onCloseIntro && (
              <button
                type="button"
                onClick={onCloseIntro}
                className="px-2.5 py-1 rounded-full bg-white border border-slate-200 text-[11.5px] font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
              >
                닫기 ✕
              </button>
            )}
          </div>
        </div>

        {/* =========================================================
            상단 중앙 검색창: 120fps 고프레임 좌→우 물결 차오름 (transition 지연 0ms)
        ========================================================= */}
        <div className="liquid-search-bar" data-testid="liquid-search-bar">
          <div
            ref={fillLayerRef}
            className="liquid-fill-layer-gpu"
            style={{ width: "100%" }}
            aria-hidden="true"
          >
            {/* 오른쪽 물결 경계면 60~120fps GPU 웨이브 크레스트 */}
            <svg
              className="liquid-wave-crest-gpu"
              viewBox="0 0 36 120"
              preserveAspectRatio="none"
            >
              <path
                d="M0,0 L18,0 C34,20 6,40 22,60 C36,80 8,100 20,120 L0,120 Z"
                fill="rgba(45, 212, 191, 0.78)"
              />
            </svg>
          </div>

          {/* 검색창 내부 (미니멀 1줄 구성) */}
          <div className="liquid-search-content">
            <div className="flex items-center gap-3 flex-1 min-w-[200px]">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#0284C7] to-[#2DD4BF] text-white flex items-center justify-center shrink-0">
                <Search className="w-4 h-4" />
              </div>
              <input
                type="text"
                value={repoInput}
                onChange={(e) => onChangeRepoInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onTriggerScan();
                }}
                className="liquid-search-input"
                placeholder="https://github.com/minji-cafe/order-site"
              />
              <span
                ref={pillBadgeRef}
                className="hidden sm:inline-block font-mono text-xs font-extrabold px-2 py-0.5 rounded-full bg-white/90 text-[#0284C7] border border-sky-200/80"
              >
                100%
              </span>
            </div>

            <button
              type="button"
              onClick={onTriggerScan}
              className="liquid-scan-btn"
            >
              <Sparkles className="w-4 h-4" />
              <span ref={btnTextRef}>물결 스캔</span>
            </button>
          </div>
        </div>

        {/* =========================================================
            하단 0% ~ 100% 카운트업 바 (미니멀 1줄 + 4단계 점등 칩)
        ========================================================= */}
        <div
          className="liquid-countup-panel-minimal"
          data-testid="liquid-countup-panel"
        >
          <div className="flex items-center justify-between gap-3">
            <span
              ref={stageTextRef}
              className="text-xs sm:text-sm font-bold text-slate-700 truncate"
            >
              ✓ 100% 스마트 스캔 완료
            </span>

            <span
              ref={countTextRef}
              className="countup-number-badge"
              data-testid="liquid-countup-value"
            >
              100%
            </span>
          </div>

          <div className="countup-sync-track">
            <div
              ref={syncFillRef}
              className="countup-sync-fill-gpu"
              style={{ width: "100%" }}
            />
          </div>

          <div className="grid grid-cols-4 gap-1.5 mt-2.5">
            {["① 소스 추출", "② 엔진 스캔", "③ GPU 검증", "④ MCP 완료"].map(
              (label, idx) => (
                <div
                  key={label}
                  ref={(el) => {
                    stepRefs.current[idx] = el;
                  }}
                  data-active="true"
                  className="minimal-step-chip"
                >
                  {label}
                </div>
              )
            )}
          </div>
        </div>
      </div>
    );
  }
);

LiquidSearchBox.displayName = "LiquidSearchBox";
