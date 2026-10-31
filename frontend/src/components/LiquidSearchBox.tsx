"use client";

import React, { useEffect, useRef, useImperativeHandle, forwardRef, useState } from "react";
import { Search, Sparkles, RotateCcw, HelpCircle, Terminal, ShieldAlert, Cpu } from "lucide-react";

export interface LiquidSearchBoxHandle {
  playAnimation: (durationMs?: number, onDone?: () => void) => void;
}

interface LiquidSearchBoxProps {
  repoInput: string;
  onChangeRepoInput: (val: string) => void;
  onTriggerScan: (customTarget?: string) => void;
  mode?: "intro" | "hero";
  onCloseIntro?: () => void;
}

// AI Spera (Criminal IP) 스타일 빠른 쿼리 태그 + VibeAppScanner 타깃 프리셋
const QUICK_CTI_QUERIES = [
  {
    tag: "repo:minji-cafe/order-site",
    value: "https://github.com/minji-cafe/order-site",
    badge: "Vibe App",
    tip: "Cursor·Lovable로 제작된 카페 주문 웹앱 (비밀키·결제변조·미인증 API 5건 탐지)",
  },
  {
    tag: "secret:supabase-service-role",
    value: "https://github.com/minji-cafe/order-site#supabase-service-role",
    badge: "Gitleaks · act",
    tip: "클라이언트 번들(NEXT_PUBLIC_*)에 노출된 Supabase service_role 관리자 키 헌팅",
  },
  {
    tag: "rule:payment-price-tamper",
    value: "https://github.com/minji-cafe/order-site#orders-route",
    badge: "Opengrep",
    tip: "브라우저 요청 금액(totalPrice) 무검증 결제 승인 취약점 스캔",
  },
  {
    tag: "cve:CVE-2025-29927",
    value: "https://github.com/minji-cafe/order-site#next-cve",
    badge: "OSV · CVE",
    tip: "package-lock.json 기반 Next.js 미들웨어 권한 우회 CVE 자동 대조",
  },
];

const getMinimalStageText = (pct: number) => {
  if (pct < 25) return "① [CTI Recon] GitHub 소스·의존성 트리 추출 중";
  if (pct < 55) return "② [4-Engine] Opengrep · OSV · Gitleaks · 설정 검사 중";
  if (pct < 85) return "③ [Agentic AI] 로컬 L4 GPU Red–Blue 공방 검증 중";
  if (pct < 100) return "④ [Zero-Retention] 원본 즉시 파기 & MCP 패치 생성 중";
  return "✓ 100% 스마트 물결 스캔 & Red–Blue 검증 완료";
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
    const [activeTag, setActiveTag] = useState<string>(QUICK_CTI_QUERIES[0].tag);

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
        {/* 상단 CTI 검색 헤더 줄 (AI Spera + AhnLab AI PLUS 스타일 결합) */}
        <div className="flex items-center justify-between gap-2 mb-2.5 px-1 flex-wrap">
          <div className="inline-flex items-center gap-2 text-xs font-bold text-[#0284C7]">
            <span className="w-2 h-2 rounded-full bg-gradient-to-r from-[#38BDF8] to-[#2DD4BF] animate-pulse" />
            <span className="font-mono tracking-tight">CTI &amp; VIBE CODE OMNI-SCANNER</span>
            <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-50 border border-sky-200/80 text-[10.5px] font-mono text-[#0369A1]">
              <Cpu className="w-3 h-3" /> L4 GPU Red–Blue Ready
            </span>
            {/* 툴팁 아이콘 */}
            <div className="group relative inline-flex items-center">
              <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-[#0284C7] cursor-help" />
              <div className="SmartTooltip">
                Criminal IP의 직관적 위협 검색창과 VibeAppScanner의 즉시 코드 진단,
                그리고 120fps 좌→우 물결 차오름(0%→100% 카운트업 동기화)을 결합한
                스마트 검색 엔진입니다.
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
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#0284C7] to-[#2DD4BF] text-white flex items-center justify-center shrink-0 shadow-xs">
                <Search className="w-4 h-4" />
              </div>
              <span className="hidden md:inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900/90 text-sky-300 font-mono text-[11px] font-bold shrink-0">
                <Terminal className="w-3 h-3 text-teal-300" />
                GitHub
              </span>
              <input
                type="text"
                value={repoInput}
                onChange={(e) => onChangeRepoInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onTriggerScan(repoInput);
                }}
                className="liquid-search-input"
                placeholder="https://github.com/minji-cafe/order-site (GitHub 저장소 URL 입력)"
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
              onClick={() => onTriggerScan(repoInput)}
              className="liquid-scan-btn"
            >
              <Sparkles className="w-4 h-4" />
              <span ref={btnTextRef}>물결 스캔</span>
            </button>
          </div>
        </div>

        {/* =========================================================
            AI Spera (Criminal IP) 스타일 원클릭 위협 쿼리 태그 바 (호버 툴팁 내장)
        ========================================================= */}
        {mode === "hero" && (
          <div className="flex items-center gap-1.5 flex-wrap mt-2.5 px-1">
            <span className="text-[11px] font-mono font-bold text-slate-400 flex items-center gap-1 mr-1">
              <ShieldAlert className="w-3.5 h-3.5 text-[#0284C7]" />
              Quick Query:
            </span>
            {QUICK_CTI_QUERIES.map((q) => {
              const isSelected = activeTag === q.tag;
              return (
                <div key={q.tag} className="group relative inline-flex">
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTag(q.tag);
                      onChangeRepoInput(q.value);
                      onTriggerScan(q.value);
                    }}
                    className={`px-2.5 py-1 rounded-lg font-mono text-[11px] font-bold transition flex items-center gap-1.5 cursor-pointer border ${
                      isSelected
                        ? "bg-gradient-to-r from-[#E0F2FE] to-[#CCFBF1] border-[#38BDF8] text-[#0369A1] shadow-2xs"
                        : "bg-white/85 border-slate-200/90 text-slate-600 hover:border-sky-300 hover:text-[#0284C7]"
                    }`}
                  >
                    <span>{q.tag}</span>
                    <span className="px-1.5 py-0.2 rounded bg-white/90 text-[10px] text-[#0D9488] font-extrabold border border-teal-200/60">
                      {q.badge}
                    </span>
                  </button>
                  <div className="SmartTooltip">{q.tip}</div>
                </div>
              );
            })}
          </div>
        )}

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
              ✓ 100% 스마트 물결 스캔 &amp; Red–Blue 검증 완료
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
            {["① 소스 추출", "② 4대 엔진", "③ GPU Red–Blue", "④ MCP 패치"].map(
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
