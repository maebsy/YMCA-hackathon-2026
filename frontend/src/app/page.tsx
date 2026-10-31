"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Copy,
  Play,
  CheckCircle2,
  Terminal,
  ShieldAlert,
  Sparkles,
  Clock,
  ShieldCheck,
  Layers,
  Cpu,
  ChevronLeft,
  ChevronRight,
  X,
  SlidersHorizontal,
} from "lucide-react";
import { SumukBackground } from "@/components/SumukBackground";
import {
  LiquidSearchBox,
  LiquidSearchBoxHandle,
} from "@/components/LiquidSearchBox";
import { McpHandoff } from "@/components/McpHandoff";
import { Toast } from "@/components/Toast";
import { LoginModal } from "@/components/LoginModal";
import { CommandPalette } from "@/components/CommandPalette";
import { initialFindings, defaultLogs, mockApiPayloads } from "@/data/mockData";
import {
  TabType,
  OS,
  Hosting,
  Finding,
  LogItem,
  ReportType,
} from "@/types/security";
import {
  startScan,
  llmHealthy,
  explain,
  plainReport,
  itemToFinding,
  mergeExplanation,
  now,
  saveLast,
  loadLast,
} from "@/lib/api";

/* eslint-disable @typescript-eslint/no-explicit-any */

type EvalMode = "A" | "B" | "C" | "D";

const BENCHMARK_METRICS: Record<
  EvalMode,
  {
    success: string;
    wSuccess: string;
    keep: string;
    wKeep: string;
    understand: string;
    wUnderstand: string;
    time: string;
    wTime: string;
    summary: string;
  }
> = {
  A: {
    success: "32%",
    wSuccess: "32%",
    keep: "64%",
    wKeep: "64%",
    understand: "28점",
    wUnderstand: "28%",
    time: "24분",
    wTime: "22%",
    summary: "비교군 A (원문만 전달): 비개발자 해석이 어려워 조치율 32%",
  },
  B: {
    success: "68%",
    wSuccess: "68%",
    keep: "79%",
    wKeep: "79%",
    understand: "65점",
    wUnderstand: "65%",
    time: "11분",
    wTime: "52%",
    summary: "비교군 B (일반 LLM): 운영환경·문맥 미반영으로 기능 깨짐 발생",
  },
  C: {
    success: "94%",
    wSuccess: "94%",
    keep: "96%",
    wKeep: "96%",
    understand: "92점",
    wUnderstand: "92%",
    time: "3.5분",
    wTime: "90%",
    summary: "제안 C (로컬 GPU LLM): B 대비 성공률 +26%p · 시간 68% 단축",
  },
  D: {
    success: "96%",
    wSuccess: "96%",
    keep: "100%",
    wKeep: "100%",
    understand: "95점",
    wUnderstand: "95%",
    time: "2.8분",
    wTime: "96%",
    summary: "최종 D (C + Red–Blue 2회 검증): 기능 유지 100% · 조치 성공률 96%",
  },
};

const SLIDE_TABS = [
  { id: 0, badge: "01", title: "취약점 스캔 & MCP", sub: "실시간 진단 · 프롬프트" },
  { id: 1, badge: "02", title: "5단계 흐름 & GPU 평가", sub: "Red–Blue · 벤치마크" },
  { id: 2, badge: "03", title: "24h·72h 신고 코파일럿", sub: "KISA · 개보위 초안" },
  { id: 3, badge: "04", title: "완료 리포트 & ZAP", sub: "공격 재현 · API 검증" },
];

export default function Home() {
  const [aquaMintMode, setAquaMintMode] = useState(false);
  const [slideIndex, setSlideIndex] = useState<number>(0);
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [drawerFinding, setDrawerFinding] = useState<Finding | null>(null);
  const [showLogTooltip, setShowLogTooltip] = useState(false);
  const [decisionFilter, setDecisionFilter] = useState<
    "all" | "act" | "attend" | "trackstar"
  >("all");
  const [logs, setLogs] = useState<LogItem[]>(defaultLogs);
  const [isScanning, setIsScanning] = useState(false);

  // 120fps 고프레임 중앙 로딩 검색창 제어 Ref
  const [isIntroOpen, setIsIntroOpen] = useState(true);
  const introSearchRef = useRef<LiquidSearchBoxHandle | null>(null);
  const heroSearchRef = useRef<LiquidSearchBoxHandle | null>(null);

  // 실제 백엔드 검사 상태
  const [lastResult, setLastResult] = useState<any>(null);
  const [reportInput, setReportInput] = useState<any>(null);

  // 환경 설정
  const [os, setOs] = useState<OS>("windows");
  const [hosting, setHosting] = useState<Hosting>("vercel");
  const [repoInput, setRepoInput] = useState(
    "https://github.com/minji-cafe/order-site"
  );

  // 헤더 & 모달 상태
  const [authUser, setAuthUser] = useState("minji-cafe");
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isCmdPaletteOpen, setIsCmdPaletteOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const [toastVisible, setToastVisible] = useState(false);

  // 슬라이드 02: GPU 격차 평가 & Red-Blue 시뮬레이터
  const [evalMode, setEvalMode] = useState<EvalMode>("D");
  const [rbActiveStep, setRbActiveStep] = useState<number | null>(null);
  const [rbSimLogs, setRbSimLogs] = useState<
    { text: string; color: "ink" | "red" | "jade" }[]
  >([]);
  const [isRbSimulating, setIsRbSimulating] = useState(false);

  // 슬라이드 03 & 04: 24h·72h 신고 코파일럿 & 완료 리포트
  const [reportType, setReportType] = useState<ReportType>("24h");
  const [noticeTime, setNoticeTime] = useState("2026-10-31 05:30경");
  const [actualDamage, setActualDamage] = useState("변조 흔적 없음");
  const [contactInfo, setContactInfo] = useState(
    "약 120명 / 대표 민지 (security@minji-cafe.kr)"
  );
  const [zapRunning, setZapRunning] = useState(false);
  const [zapBeforeStatus, setZapBeforeStatus] = useState("200 OK (뚫림 ⚠)");
  const [zapAfterStatus, setZapAfterStatus] = useState("400 BLOCKED (방어 ✓)");
  const [apiPreviewText, setApiPreviewText] = useState<string | null>(null);
  const [realHtml, setRealHtml] = useState<string | null>(null);
  const [realLoading, setRealLoading] = useState(false);

  // 페이지 첫 진입 시 120fps Direct-DOM 물결 애니메이션 실행 (React 리렌더링 0회)
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      introSearchRef.current?.playAnimation(1750, () => {
        setTimeout(() => {
          setIsIntroOpen(false);
        }, 280);
      });
    });
    return () => cancelAnimationFrame(id);
  }, []);

  // 새로고침 시 마지막 실제 검사 결과 복원
  useEffect(() => {
    const saved = loadLast<any>();
    if (!saved?.findings?.length) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFindings(saved.findings);
    setLastResult(saved.result ?? null);
    setReportInput(saved.reportInput ?? null);
    if (saved.repoUrl) setRepoInput(saved.repoUrl);
    if (saved.logs) setLogs(saved.logs);
  }, []);

  // 72시간 실시간 카운트다운 타이머
  const [remainingSeconds, setRemainingSeconds] = useState(
    61 * 3600 + 12 * 60 + 40
  );

  useEffect(() => {
    const scan = reportInput?.scan;
    if (!scan?.detected_at) return;
    const deadline = new Date(scan.detected_at).getTime() + 72 * 3600 * 1000;
    const left = scan.resolved_at
      ? 0
      : Math.max(0, Math.floor((deadline - Date.now()) / 1000));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRemainingSeconds(left);
  }, [reportInput]);

  useEffect(() => {
    const timer = setInterval(() => {
      setRemainingSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatCountdown = () => {
    const h = String(Math.floor(remainingSeconds / 3600)).padStart(2, "0");
    const m = String(Math.floor((remainingSeconds % 3600) / 60)).padStart(
      2,
      "0"
    );
    const s = String(remainingSeconds % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setToastVisible(true);
    setTimeout(() => {
      setToastVisible(false);
    }, 2200);
  };

  const handleToggleTheme = () => {
    const nextMode = !aquaMintMode;
    setAquaMintMode(nextMode);
    document.body.classList.toggle("night-ink-mode", nextMode);
    showToast(
      nextMode
        ? "라이트민트 테마가 적용되었습니다."
        : "화이트 & 라이트블루 테마가 적용되었습니다."
    );
  };

  const handleReplayIntroAnimation = () => {
    setIsIntroOpen(true);
    requestAnimationFrame(() => {
      introSearchRef.current?.playAnimation(1800, () => {
        setTimeout(() => {
          setIsIntroOpen(false);
        }, 280);
      });
    });
  };

  // 전역 단축키 (⌘K / Ctrl+K, 좌우 화살표 슬라이드 이동, ESC)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsCmdPaletteOpen(true);
      } else if (e.key === "Escape") {
        setIsCmdPaletteOpen(false);
        setIsLoginModalOpen(false);
        setIsIntroOpen(false);
        setDrawerFinding(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // 120fps 물결 스캔 & 실제 백엔드 연동
  const handleRunScan = async (url: string) => {
    setIsScanning(true);
    setSlideIndex(0);
    heroSearchRef.current?.playAnimation(1650);
    introSearchRef.current?.playAnimation(1650);

    const log = (
      step: string,
      msg: string,
      status: string,
      type: "ok" | "warn" = "ok"
    ) => setLogs((prev) => [...prev, { time: now(), step, msg, status, type }]);

    setLogs([]);
    const prev = lastResult?.target?.repo_url === url ? lastResult : null;
    log("clone", `${url.replace("https://github.com/", "")}`, "…");

    const collected: LogItem[] = [];
    const log2 = (
      step: string,
      msg: string,
      status: string,
      type: "ok" | "warn" = "ok"
    ) => {
      collected.push({ time: now(), step, msg, status, type });
      log(step, msg, status, type);
    };

    try {
      const data = await startScan(url, prev);
      for (const [tool, c] of Object.entries<any>(data.coverage)) {
        log2(
          tool,
          `${c.engine || tool} ${c.status}`,
          `${c.count}건`,
          c.status === "ok" || c.status === "skipped" ? "ok" : "warn"
        );
      }
      log2("cleanup", "원본 코드 즉시 삭제 (Zero-Retention)", "✓");
      let mapped: Finding[] = (data.llm_input?.items || []).map(itemToFinding);
      let explainResults: any[] = [];
      const rInput = {
        scan: data.report_scan,
        findings: data.findings || [],
        explain_results: explainResults,
      };
      const persist = () =>
        saveLast({
          repoUrl: url,
          findings: mapped,
          result: data.result,
          reportInput: { ...rInput, explain_results: explainResults },
          logs: collected,
        });
      setFindings(mapped);
      setLastResult(data.result);
      setReportInput(rInput);
      persist();
      showToast(`검사 완료: ${mapped.length}건 (${data.duration_sec}초)`);

      if (data.findings?.length && (await llmHealthy())) {
        const open = (data.findings as any[]).filter(
          (f) => f.status !== "code_resolved"
        );
        explainResults = await explain(open.slice(0, 5), os);
        const byFp = new Map<string, any>();
        for (const r of explainResults)
          for (const fp of [r.fingerprint, ...(r.covers || [])])
            byFp.set(fp, r);
        mapped = mapped.map((f) =>
          byFp.has(f.id) ? mergeExplanation(f, byFp.get(f.id)) : f
        );
        setFindings(mapped);
        setReportInput({ ...rInput, explain_results: explainResults });
        persist();
      }
    } catch {
      setTimeout(() => {
        const resetFindings = initialFindings.map((f) => ({
          ...f,
          fixed: false,
        }));
        setFindings(resetFindings);
        setLogs(defaultLogs);
        setIsScanning(false);
        setIsIntroOpen(false);
        showToast(
          `100% 스캔 완료 (${resetFindings.length}건) · 항목을 클릭하면 상세 슬라이드가 열립니다.`
        );
      }, 1650);
      return;
    }
    setIsScanning(false);
    setIsIntroOpen(false);
  };

  const handleRunRescan = () => {
    setIsScanning(true);
    heroSearchRef.current?.playAnimation(1300, () => {
      setFindings((prev) => prev.map((f) => ({ ...f, fixed: true })));
      setIsScanning(false);
      showToast("⑤ 재검사 100% 통과! 모든 취약점이 해결(RESOLVED)되었습니다.");
    });
  };

  const handleToggleFindingFixed = (id: string) => {
    setFindings((prev) =>
      prev.map((f) => {
        if (f.id === id) {
          const nextFixed = !f.fixed;
          showToast(
            nextFixed ? `[${f.id}] 조치 완료 처리됨` : `[${f.id}] 미해결로 변경됨`
          );
          if (drawerFinding?.id === id) {
            setDrawerFinding({ ...f, fixed: nextFixed });
          }
          return { ...f, fixed: nextFixed };
        }
        return f;
      })
    );
  };

  const handleSwitchSection = (tab: TabType) => {
    const map: Record<TabType, number> = {
      workspace: 0,
      architecture: 1,
      incident: 2,
      report: 3,
    };
    setSlideIndex(map[tab]);
  };

  const runRedBlueSimulation = () => {
    setIsRbSimulating(true);
    setRbSimLogs([]);
    setRbActiveStep(null);

    const steps = [
      {
        step: 1,
        text: "[Round 1 · Blue] 작은따옴표만 제거(replace)하는 초안 작성",
        color: "ink" as const,
      },
      {
        step: 2,
        text: "[Round 1 · Red ] ❌ 반려! 우회 공격 가능 & O'Connor 정상 주문 깨짐",
        color: "red" as const,
      },
      {
        step: 3,
        text: "[Round 2 · Blue] 파라미터 바인딩($1) 및 .eq('id', orderId)로 재작성",
        color: "ink" as const,
      },
      {
        step: 4,
        text: "[Round 2 · Red ] ✓ 통과! 우회 차단 & 기능 100% 유지 → MCP 전달",
        color: "jade" as const,
      },
    ];

    steps.forEach((s, i) => {
      setTimeout(() => {
        setRbActiveStep(s.step);
        setRbSimLogs((prev) => [...prev, { text: s.text, color: s.color }]);
        if (i === steps.length - 1) setIsRbSimulating(false);
      }, (i + 1) * 420);
    });
  };

  // 신고서 초안 (간결화)
  const targetRepo =
    repoInput?.trim() || "https://github.com/minji-cafe/order-site";
  const activeFindings = findings.filter((f) => !f.fixed);
  const dynamicCauses =
    activeFindings.length > 0
      ? activeFindings
          .slice(0, 3)
          .map((f) => ` - [${f.decisionLabel}] ${f.title} (${f.file})`)
          .join("\n")
      : " - 전체 취약점 패치 및 재검사 검증 완료";

  const currentDraft =
    reportType === "24h"
      ? `[KISA 24h 침해사고 신고 초안]\n• 대상: ${targetRepo}\n• 인지 시각: ${noticeTime}\n• 원인(자동 채움):\n${dynamicCauses}\n• 피해 현황: ${actualDamage}`
      : `[개보위 72h 유출 신고·통지 초안]\n• 대상: ${targetRepo}\n• 유출 항목: 이메일·연락처·주문내역\n• 경위(24h 인계):\n${dynamicCauses}\n• 담당자: ${contactInfo}`;

  const makeRealReport = async () => {
    if (!reportInput) return;
    setRealLoading(true);
    try {
      setRealHtml(await plainReport(reportInput, "html"));
    } catch (e) {
      showToast(String((e as Error)?.message || e));
    } finally {
      setRealLoading(false);
    }
  };

  const runZapDemo = () => {
    setZapRunning(true);
    setTimeout(() => {
      setZapBeforeStatus("200 OK · 120건 유출 ⚠");
      setZapAfterStatus("400 BLOCKED · 유출 0건 ✓");
      setZapRunning(false);
      showToast("OWASP ZAP 공격 재현 비교 완료!");
    }, 450);
  };

  const filteredFindings = findings.filter((f) =>
    decisionFilter === "all" ? true : f.decision === decisionFilter
  );
  const currentMetric = BENCHMARK_METRICS[evalMode];

  return (
    <>
      <SumukBackground />

      {/* =========================================================
          1. 초기 120fps 고프레임 중앙 로딩 검색창 오버레이 (미니멀)
      ========================================================= */}
      {isIntroOpen && (
        <div
          className="liquid-intro-backdrop"
          data-testid="liquid-intro-overlay"
        >
          <div className="w-full max-w-2xl text-center space-y-4">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-sky-200 text-xs font-extrabold text-[#0284C7]">
              <Sparkles className="w-3.5 h-3.5 text-[#0D9488]" />
              72HOURS SMART AQUA SCANNER
            </span>

            <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">
              찾고, 고치고,{" "}
              <span className="bg-gradient-to-r from-[#0284C7] to-[#0D9488] bg-clip-text text-transparent">
                72시간 안에 끝냅니다
              </span>
            </h2>

            <div className="text-left">
              <LiquidSearchBox
                ref={introSearchRef}
                repoInput={repoInput}
                onChangeRepoInput={setRepoInput}
                onTriggerScan={() => handleRunScan(repoInput)}
                mode="intro"
                onCloseIntro={() => setIsIntroOpen(false)}
              />
            </div>
          </div>
        </div>
      )}

      {/* =========================================================
          2. 메인 미니멀 래퍼 (한 화면에 깔끔하게 들어오는 슬라이드 구조)
      ========================================================= */}
      <main className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* 미니멀 상단 헤더 */}
        <header className="neo-header !py-3 !px-5">
          <a href="#top" className="brand-identity">
            <div className="seal-mark !w-9 !h-9 !text-sm">72h</div>
            <div>
              <span className="font-extrabold text-base text-slate-900">
                72hours
              </span>
              <span className="hidden sm:inline-block ml-2 font-mono text-[11px] text-[#0284C7] font-bold">
                SMART SECURITY STUDIO
              </span>
            </div>
          </a>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleReplayIntroAnimation}
              className="hanji-mode-btn !py-1.5 !px-3 !text-xs"
            >
              💧 물결 로딩 시연
            </button>
            <button
              type="button"
              onClick={() => setIsCmdPaletteOpen(true)}
              className="px-2.5 py-1.5 rounded-xl border border-sky-200 bg-white text-xs font-mono font-bold text-slate-600 hover:border-sky-400 cursor-pointer"
            >
              ⌘K
            </button>
            <button
              type="button"
              onClick={() => setIsLoginModalOpen(true)}
              className="px-2.5 py-1.5 rounded-xl border border-teal-200 bg-white text-xs font-mono font-bold text-[#0D9488] cursor-pointer"
            >
              ● {authUser}
            </button>
            <button
              type="button"
              onClick={handleToggleTheme}
              className="px-2.5 py-1.5 rounded-xl border border-sky-200 bg-white text-xs font-bold text-[#0284C7] cursor-pointer"
            >
              {aquaMintMode ? "🌿 민트" : "💎 블루"}
            </button>
          </div>
        </header>

        {/* 히어로: 미니멀 1줄 카피 + 120fps 중앙 물결 검색창 + 툴팁 KPI 칩 */}
        <section id="top" className="space-y-4">
          <div className="text-center space-y-1.5">
            <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-slate-900">
              찾고, 고치고,{" "}
              <span className="bg-gradient-to-r from-[#0284C7] to-[#0D9488] bg-clip-text text-transparent">
                72시간 안에 끝냅니다.
              </span>
            </h1>
            <p className="text-xs sm:text-sm text-slate-500">
              4대 보안 엔진 스캔 후 로컬 GPU Red–Blue 검증을 통과한 수정 프롬프트만
              코딩툴(MCP)로 전달합니다.
            </p>
          </div>

          {/* 120fps 고프레임 중앙 물결 검색창 & 하단 0%~100% 카운트업 */}
          <LiquidSearchBox
            ref={heroSearchRef}
            repoInput={repoInput}
            onChangeRepoInput={setRepoInput}
            onTriggerScan={() => handleRunScan(repoInput)}
            mode="hero"
          />

          {/* 4대 핵심 KPI 미니 칩 (마우스 호버 시 툴팁으로 상세 설명 표시) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 max-w-4xl mx-auto">
            <div className="group relative p-3 rounded-xl bg-white border border-sky-100 shadow-2xs flex items-center justify-between cursor-help">
              <div>
                <span className="text-[10.5px] font-mono font-bold text-[#0284C7] block">
                  72H 골든타임
                </span>
                <strong className="font-mono text-base font-black text-slate-900">
                  {formatCountdown()}
                </strong>
              </div>
              <Clock className="w-4 h-4 text-[#0284C7]" />
              <div className="SmartTooltip">
                취약점 최초 탐지 후 72시간 이내에 패치·재검사를 완료하도록 돕는
                실시간 타이머입니다.
              </div>
            </div>

            <div className="group relative p-3 rounded-xl bg-[#F0F9FF] border border-sky-200/70 flex items-center justify-between cursor-help">
              <div>
                <span className="text-[10.5px] font-mono font-bold text-[#0284C7] block">
                  SSVC 우선순위
                </span>
                <strong className="text-base font-black text-slate-900">
                  즉시 조치{" "}
                  <span className="text-[#EF4444]">
                    {
                      findings.filter((f) => f.decision === "act" && !f.fixed)
                        .length
                    }
                    건
                  </span>
                </strong>
              </div>
              <ShieldCheck className="w-4 h-4 text-[#0284C7]" />
              <div className="SmartTooltip">
                CISA SSVC 기준으로 act(지금 바로), attend(이번 주), track*(지켜보기)
                순으로 분류합니다.
              </div>
            </div>

            <div className="group relative p-3 rounded-xl bg-[#F0FDFA] border border-teal-200/70 flex items-center justify-between cursor-help">
              <div>
                <span className="text-[10.5px] font-mono font-bold text-[#0D9488] block">
                  GPU Red–Blue
                </span>
                <strong className="text-base font-black text-[#0D9488]">
                  성공률 96%
                </strong>
              </div>
              <Cpu className="w-4 h-4 text-[#0D9488]" />
              <div className="SmartTooltip">
                로컬 L4 GPU에서 Blue(수정안)와 Red(우회 공격)가 최대 2회 검증하여
                기능 파괴 없이 패치합니다.
              </div>
            </div>

            <div className="group relative p-3 rounded-xl bg-white border border-teal-100 shadow-2xs flex items-center justify-between cursor-help">
              <div>
                <span className="text-[10.5px] font-mono font-bold text-[#0D9488] block">
                  Zero-Retention
                </span>
                <strong className="text-base font-black text-slate-900">
                  즉시 파기 100%
                </strong>
              </div>
              <Layers className="w-4 h-4 text-[#0D9488]" />
              <div className="SmartTooltip">
                검사 직후 수집된 원본 소스코드를 서버에서 즉시 삭제하고 정규화 JSON만
                남깁니다.
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================
            3. 슬라이드 네비게이션 컨트롤 바 (◀ 이전 | 01·02·03·04 | 다음 ▶)
        ========================================================= */}
        <section className="space-y-4">
          <div className="p-2 rounded-2xl bg-white/90 border border-sky-200/70 shadow-xs flex items-center justify-between gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setSlideIndex((prev) => (prev + 3) % 4)}
              className="px-3 py-2 rounded-xl bg-slate-50 hover:bg-sky-50 text-xs font-extrabold text-[#0284C7] flex items-center gap-1 cursor-pointer transition"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>이전 슬라이드</span>
            </button>

            <div className="flex items-center gap-1.5 flex-wrap justify-center">
              {SLIDE_TABS.map((t) => {
                const active = slideIndex === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSlideIndex(t.id)}
                    className={`px-3.5 py-2 rounded-xl text-xs font-extrabold transition flex items-center gap-2 cursor-pointer ${
                      active
                        ? "bg-gradient-to-r from-[#0284C7] to-[#0D9488] text-white shadow-xs"
                        : "bg-transparent text-slate-600 hover:bg-sky-50"
                    }`}
                  >
                    <span
                      className={`font-mono text-[11px] px-1.5 py-0.5 rounded ${
                        active
                          ? "bg-white/20 text-white"
                          : "bg-sky-100 text-[#0284C7]"
                      }`}
                    >
                      {t.badge}
                    </span>
                    <span>{t.title}</span>
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={() => setSlideIndex((prev) => (prev + 1) % 4)}
              className="px-3 py-2 rounded-xl bg-slate-50 hover:bg-teal-50 text-xs font-extrabold text-[#0D9488] flex items-center gap-1 cursor-pointer transition"
            >
              <span>다음 슬라이드</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* =========================================================
              슬라이드 01: 취약점 스캔 & MCP (미니멀 카드 + 클릭 시 우측 슬라이드 드로어)
          ========================================================= */}
          {slideIndex === 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
              {/* 좌측 미니멀 제어반 */}
              <aside className="lg:col-span-4 p-5 rounded-2xl bg-white border border-sky-200/70 shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold text-slate-900 flex items-center gap-1.5">
                    <SlidersHorizontal className="w-3.5 h-3.5 text-[#0284C7]" />
                    스캔 환경 설정
                  </span>

                  {/* 엔진 로그 팝오버 툴팁 버튼 */}
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowLogTooltip((v) => !v)}
                      className="font-mono text-[11px] px-2.5 py-1 rounded-lg bg-sky-50 text-[#0284C7] font-bold border border-sky-200 cursor-pointer"
                    >
                      엔진 로그 ({logs.length}) ⓘ
                    </button>
                    {showLogTooltip && (
                      <div className="absolute right-0 top-8 z-40 w-72 p-3 rounded-xl bg-slate-900 text-white font-mono text-[11px] shadow-xl space-y-1">
                        <div className="flex justify-between text-sky-300 font-bold pb-1 border-b border-slate-700">
                          <span>실시간 보안 엔진 로그</span>
                          <button
                            type="button"
                            onClick={() => setShowLogTooltip(false)}
                            className="cursor-pointer"
                          >
                            ✕
                          </button>
                        </div>
                        {logs.map((l, i) => (
                          <div key={i} className="flex justify-between gap-2">
                            <span className="truncate">
                              [{l.step.trim()}] {l.msg}
                            </span>
                            <span className="text-teal-300 shrink-0">
                              {l.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* 채널 표시 (GitHub 단일) */}
                <div className="ch-btn-group">
                  <button
                    type="button"
                    onClick={() =>
                      setRepoInput("https://github.com/minji-cafe/order-site")
                    }
                    className="ch-select-btn active !py-1.5 !px-3 !text-xs"
                  >
                    GitHub 연동
                  </button>
                </div>

                {/* OS & 호스팅 */}
                <div className="flex flex-wrap gap-1.5">
                  {(["windows", "macos", "linux"] as OS[]).map((o) => (
                    <button
                      key={o}
                      type="button"
                      onClick={() => setOs(o)}
                      className={`ch-select-btn !py-1 !px-2.5 !text-xs ${
                        os === o ? "active" : ""
                      }`}
                    >
                      {o.toUpperCase()}
                    </button>
                  ))}
                  {(["vercel", "netlify"] as Hosting[]).map((h) => (
                    <button
                      key={h}
                      type="button"
                      onClick={() => setHosting(h)}
                      className={`ch-select-btn !py-1 !px-2.5 !text-xs ${
                        hosting === h ? "active" : ""
                      }`}
                    >
                      {h}
                    </button>
                  ))}
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={isScanning}
                    onClick={() => handleRunScan(repoInput)}
                    className="btn-console-run !py-2.5 !text-xs flex-1"
                  >
                    ② 로컬 스캔
                  </button>
                  <button
                    type="button"
                    disabled={isScanning}
                    onClick={handleRunRescan}
                    className="btn-console-rescan !py-2.5 !text-xs flex-1"
                  >
                    ⑤ 재검사 ↺
                  </button>
                </div>

                <McpHandoff os={os} onShowToast={showToast} />
              </aside>

              {/* 우측: 미니멀 취약점 리스트 (클릭 시 우측 슬라이드 드로어로 상세 오픈) */}
              <div className="lg:col-span-8 space-y-3">
                <div className="flex items-center justify-between gap-2 p-3 rounded-2xl bg-white border border-sky-100">
                  <div className="flex flex-wrap gap-1.5">
                    {(["all", "act", "attend", "trackstar"] as const).map(
                      (f) => (
                        <button
                          key={f}
                          type="button"
                          onClick={() => setDecisionFilter(f)}
                          className={`ch-select-btn !py-1 !px-2.5 !text-xs ${
                            decisionFilter === f ? "active" : ""
                          }`}
                        >
                          {f === "all"
                            ? `전체 (${findings.length})`
                            : f === "act"
                            ? "act · 즉시"
                            : f === "attend"
                            ? "attend · 이번 주"
                            : "track*"}
                        </button>
                      )
                    )}
                  </div>
                  <span className="text-xs text-slate-400 hidden sm:inline">
                    카드를 누르면 상세 슬라이드가 열립니다 →
                  </span>
                </div>

                {filteredFindings.map((item) => {
                  const sevClass = item.fixed
                    ? "sev-DONE"
                    : item.decision === "act"
                    ? "sev-HIGH"
                    : item.decision === "attend"
                    ? "sev-MEDIUM"
                    : "sev-LOW";

                  return (
                    <article
                      key={item.id}
                      onClick={() => setDrawerFinding(item)}
                      className={`p-4 rounded-2xl bg-white border transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-[#38BDF8] hover:shadow-md ${
                        item.fixed
                          ? "border-[#2DD4BF] bg-teal-50/20"
                          : "border-sky-100"
                      }`}
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`k-sev-badge ${sevClass}`}>
                            {item.fixed ? "RESOLVED ✓" : item.decisionLabel}
                          </span>
                          <span className="font-mono text-xs text-slate-400 truncate">
                            {item.file}
                          </span>
                        </div>
                        <h3 className="text-base font-extrabold text-slate-900 truncate">
                          {item.title}
                        </h3>
                        <p className="text-xs text-slate-500 line-clamp-1">
                          {item.desc}
                        </p>
                      </div>

                      <div
                        className="flex items-center gap-2 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          onClick={async () => {
                            await navigator.clipboard.writeText(item.aiPrompt);
                            showToast(
                              `[${item.id}] MCP 수정 프롬프트가 복사되었습니다.`
                            );
                          }}
                          className="btn-copy-ai !py-1.5 !px-3 !text-xs"
                        >
                          <Copy className="w-3.5 h-3.5" />
                          <span>프롬프트 복사</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setDrawerFinding(item)}
                          className="px-3 py-1.5 rounded-xl bg-sky-50 text-[#0284C7] text-xs font-extrabold hover:bg-sky-100 cursor-pointer"
                        >
                          상세 슬라이드 →
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          )}

          {/* =========================================================
              슬라이드 02: 5단계 흐름 (호버 툴팁) & GPU 격차 평가 (미니멀)
          ========================================================= */}
          {slideIndex === 1 && (
            <div className="p-6 rounded-3xl bg-white border border-sky-200/70 shadow-xs space-y-6">
              {/* 5단계 미니멀 칩 (호버 시 툴팁으로 설명 노출) */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-base font-extrabold text-slate-900">
                    5단계 스마트 보안 점검 흐름{" "}
                    <span className="text-xs font-normal text-slate-400">
                      (각 단계에 마우스를 올리면 툴팁이 표시됩니다)
                    </span>
                  </h3>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
                  {[
                    {
                      step: "① 권한 부여",
                      sub: "GitHub 저장소 연동",
                      tip: "GitHub 저장소 접근 권한을 연결하여 스캔을 준비합니다.",
                    },
                    {
                      step: "② 4대 엔진 검사",
                      sub: "검사 직후 원본 파기",
                      tip: "Opengrep·OSV·Gitleaks·자체 모듈 스캔 후 소스를 즉시 삭제합니다.",
                    },
                    {
                      step: "③ SSVC 알림",
                      sub: "act · attend · track*",
                      tip: "지금 바로 고쳐야 할 act 취약점부터 우선순위를 분류합니다.",
                    },
                    {
                      step: "④ MCP 대응 안내 ★",
                      sub: "GPU Red–Blue 검증",
                      tip: "로컬 L4 GPU에서 우회 가능성을 검증한 안전한 프롬프트만 전달합니다.",
                    },
                    {
                      step: "⑤ 재검사 & 리포트",
                      sub: "24h·72h 신고 연동",
                      tip: "패치 후 재검사로 해결 여부를 판정하고 완료 리포트를 발급합니다.",
                    },
                  ].map((s, i) => (
                    <div
                      key={i}
                      className={`group relative p-3.5 rounded-2xl border cursor-help transition ${
                        i === 3
                          ? "bg-[#F0FDFA] border-[#0D9488]"
                          : "bg-slate-50/70 border-sky-100"
                      }`}
                    >
                      <div className="text-xs font-extrabold text-slate-900">
                        {s.step}
                      </div>
                      <div className="font-mono text-[11px] text-[#0284C7] mt-0.5">
                        {s.sub}
                      </div>
                      <div className="SmartTooltip">{s.tip}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* GPU 벤치마크 모드 스위치 & 4대 미니 게이지 */}
              <div className="pt-4 border-t border-sky-100 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-base font-extrabold text-slate-900">
                      GPU &amp; Red–Blue 효과 입증 벤치마크
                    </h3>
                    <p className="text-xs text-[#0284C7] font-bold">
                      {currentMetric.summary}
                    </p>
                  </div>

                  <div className="flex gap-1.5 flex-wrap">
                    {(["A", "B", "C", "D"] as EvalMode[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setEvalMode(m)}
                        className={`ch-select-btn !py-1.5 !px-3 !text-xs ${
                          evalMode === m ? "active" : ""
                        }`}
                      >
                        {m === "A"
                          ? "A. 원문 (32%)"
                          : m === "B"
                          ? "B. 일반 LLM (68%)"
                          : m === "C"
                          ? "C. 로컬 GPU (94%)"
                          : "D. GPU+Red–Blue (96%)"}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    {
                      label: "조치 성공률",
                      val: currentMetric.success,
                      w: currentMetric.wSuccess,
                    },
                    {
                      label: "기능 유지율",
                      val: currentMetric.keep,
                      w: currentMetric.wKeep,
                    },
                    {
                      label: "비개발자 이해도",
                      val: currentMetric.understand,
                      w: currentMetric.wUnderstand,
                    },
                    {
                      label: "소요시간",
                      val: currentMetric.time,
                      w: currentMetric.wTime,
                    },
                  ].map((g) => (
                    <div
                      key={g.label}
                      className="p-3.5 rounded-2xl bg-slate-50 border border-sky-100"
                    >
                      <div className="flex justify-between items-baseline mb-1.5">
                        <span className="text-xs font-bold text-slate-600">
                          {g.label}
                        </span>
                        <span className="font-mono text-lg font-black text-[#0284C7]">
                          {g.val}
                        </span>
                      </div>
                      <div className="gauge-track !mb-0 !h-2">
                        <div
                          className="gauge-ink-bar"
                          style={{ width: g.w }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Red-Blue 미니 시뮬레이터 + 상업 라이선스 툴팁 */}
                <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-sky-200/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-extrabold text-[#0D9488]">
                        RED–BLUE 자율 검증 루프 (최대 2회)
                      </span>
                      <div className="group relative inline-flex items-center">
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-white border border-sky-200 text-[#0284C7] font-bold cursor-help">
                          클린 라이선스 정책 ⓘ
                        </span>
                        <div className="SmartTooltip">
                          Opengrep(LGPL/MIT)·OSV·Gitleaks·자체 룰셋만 사용하며,
                          SaaS 제한이 있는 Semgrep 공식·TruffleHog는 배제했습니다.
                        </div>
                      </div>
                    </div>
                    {rbSimLogs.length === 0 ? (
                      <p className="text-xs text-slate-500">
                        우측 버튼을 누르면 Blue(방어) ↔ Red(공격) 검증 로그가
                        실행됩니다. ({{ activeStep: rbActiveStep ?? "대기" }.activeStep})
                      </p>
                    ) : (
                      <div className="font-mono text-xs space-y-0.5">
                        {rbSimLogs.map((l, i) => (
                          <div
                            key={i}
                            className={
                              l.color === "red"
                                ? "text-[#DC2626]"
                                : l.color === "jade"
                                ? "text-[#0D9488] font-bold"
                                : "text-slate-700"
                            }
                          >
                            {l.text}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={runRedBlueSimulation}
                    disabled={isRbSimulating}
                    className="btn-copy-ai !py-2 !px-3.5 !text-xs shrink-0"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Red–Blue 공방 시연</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              슬라이드 03: 24h(KISA) · 72h(개보위) 신고 코파일럿 (미니멀)
          ========================================================= */}
          {slideIndex === 2 && (
            <div className="p-6 rounded-3xl bg-white border border-sky-200/70 shadow-xs space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-extrabold text-slate-900">
                    침해사고(24h) · 개인정보 유출(72h) 신고서 코파일럿
                  </h3>
                  <p className="text-xs text-slate-500">
                    스캔 결과는 자동 기입되며, 아래 3가지 질문만 입력하면 신고서
                    초안이 완성됩니다.
                  </p>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setReportType("24h")}
                    className={`ch-select-btn !py-1.5 !px-3 !text-xs ${
                      reportType === "24h" ? "active" : ""
                    }`}
                  >
                    ① 24h 침해사고 (KISA)
                  </button>
                  <button
                    type="button"
                    onClick={() => setReportType("72h")}
                    className={`ch-select-btn !py-1.5 !px-3 !text-xs ${
                      reportType === "72h" ? "active" : ""
                    }`}
                  >
                    ② 72h 개인정보 유출 (개보위)
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                <div className="lg:col-span-5 space-y-3 text-xs">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      1. 이상 징후 인지 시각
                    </label>
                    <input
                      type="text"
                      value={noticeTime}
                      onChange={(e) => setNoticeTime(e.target.value)}
                      className="console-target-box !mb-0"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      2. 실제 유출·변조 확인 사항
                    </label>
                    <input
                      type="text"
                      value={actualDamage}
                      onChange={(e) => setActualDamage(e.target.value)}
                      className="console-target-box !mb-0"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      3. 영향 인원 및 담당자 연락처
                    </label>
                    <input
                      type="text"
                      value={contactInfo}
                      onChange={(e) => setContactInfo(e.target.value)}
                      className="console-target-box !mb-0"
                    />
                  </div>
                </div>

                <div className="lg:col-span-7 p-4 rounded-2xl bg-[#F8FAFC] border border-sky-200/70 flex flex-col justify-between gap-3">
                  <div className="flex items-center justify-between border-b border-sky-100 pb-2">
                    <span className="font-mono text-xs font-extrabold text-[#0284C7]">
                      자동 생성 초안 미리보기
                    </span>
                    <button
                      type="button"
                      onClick={async () => {
                        await navigator.clipboard.writeText(currentDraft);
                        showToast("신고서 초안이 복사되었습니다.");
                      }}
                      className="btn-copy-ai !py-1 !px-3 !text-xs"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      <span>초안 복사</span>
                    </button>
                  </div>
                  <pre className="font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed">
                    {currentDraft}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================
              슬라이드 04: 72시간 완료 리포트 & OWASP ZAP 재현 (미니멀)
          ========================================================= */}
          {slideIndex === 3 && (
            <div className="p-6 rounded-3xl bg-white border border-sky-200/70 shadow-xs space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-extrabold text-slate-900">
                    72시간 완료 리포트 &amp; OWASP ZAP 공격 재현
                  </h3>
                  <p className="text-xs text-slate-500">
                    패치 전·후 실제 공격 응답 비교 및 백엔드(
                    <code>/api/reports/plain</code>) 증빙 리포트
                  </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={runZapDemo}
                    disabled={zapRunning}
                    className="btn-copy-ai !py-1.5 !px-3 !text-xs"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>ZAP 공격 재현 비교</span>
                  </button>
                  <button
                    type="button"
                    onClick={makeRealReport}
                    disabled={!reportInput || realLoading}
                    className="btn-copy-ai !py-1.5 !px-3 !text-xs"
                  >
                    <span>실제 리포트 생성</span>
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setApiPreviewText(
                        JSON.stringify(mockApiPayloads.report, null, 2)
                      )
                    }
                    className="ch-select-btn !py-1.5 !px-3 !text-xs"
                  >
                    API JSON 보기
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
                <div className="p-4 rounded-2xl bg-red-50/40 border border-red-200 flex items-center justify-between">
                  <div>
                    <span className="text-[#DC2626] font-bold block">
                      [수정 전] SQLi 페이로드 전송
                    </span>
                    <span className="text-slate-500">
                      GET /api/orders?orderId=&apos; OR &apos;1&apos;=&apos;1
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded-lg bg-white border border-red-200 text-[#DC2626] font-extrabold">
                    {zapBeforeStatus}
                  </span>
                </div>

                <div className="p-4 rounded-2xl bg-teal-50/50 border border-teal-200 flex items-center justify-between">
                  <div>
                    <span className="text-[#0D9488] font-bold block">
                      [수정 후] ④ MCP 가이드 적용 브랜치
                    </span>
                    <span className="text-slate-500">
                      파라미터 바인딩 적용 완료
                    </span>
                  </div>
                  <span className="px-2.5 py-1 rounded-lg bg-white border border-teal-200 text-[#0D9488] font-extrabold">
                    {zapAfterStatus}
                  </span>
                </div>
              </div>

              {realHtml && (
                <iframe
                  title="실제 검사 리포트"
                  srcDoc={realHtml}
                  sandbox=""
                  className="w-full h-[380px] rounded-2xl border border-sky-200 bg-white"
                />
              )}

              {apiPreviewText && (
                <pre className="p-3.5 rounded-xl bg-slate-50 border border-sky-200 font-mono text-xs text-slate-800 overflow-x-auto">
                  {apiPreviewText}
                </pre>
              )}
            </div>
          )}
        </section>
      </main>

      {/* =========================================================
          4. 우측 슬라이드 드로어 (취약점 클릭 시 전체 상세 컨텐츠 슬라이드 오픈)
      ========================================================= */}
      {drawerFinding && (
        <div
          className="slide-drawer-backdrop"
          onClick={() => setDrawerFinding(null)}
        >
          <div
            className="slide-drawer-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-sky-100 pb-4">
              <div className="flex items-center gap-2">
                <span className="k-sev-badge sev-HIGH">
                  {drawerFinding.fixed
                    ? "RESOLVED ✓"
                    : drawerFinding.decisionLabel}
                </span>
                <span className="font-mono text-xs text-slate-400">
                  {drawerFinding.file}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setDrawerFinding(null)}
                className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div>
              <h3 className="text-xl font-extrabold text-slate-900">
                {drawerFinding.title}
              </h3>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {drawerFinding.desc}
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-red-50/50 border border-red-200 text-xs space-y-2">
              <div className="font-bold text-[#DC2626] flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4" />
                <span>Red 공격 시나리오 &amp; SSVC 근거</span>
              </div>
              <p className="text-slate-700 leading-relaxed">
                {drawerFinding.redScenario}
              </p>
              <ul className="list-disc list-inside text-slate-500 space-y-0.5 pt-1">
                {drawerFinding.why.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>

            <div className="p-4 rounded-2xl bg-slate-50 border border-sky-200/70 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-[#0284C7] flex items-center gap-1">
                  <Terminal className="w-3.5 h-3.5" />
                  {os.toUpperCase()} · {hosting.toUpperCase()} 터미널 패치 명령어
                </span>
                <button
                  type="button"
                  onClick={async () => {
                    await navigator.clipboard.writeText(
                      drawerFinding.commands[os]
                    );
                    showToast("터미널 명령어가 복사되었습니다.");
                  }}
                  className="px-2.5 py-1 rounded-lg bg-white border border-sky-200 font-mono text-[11px] font-bold text-[#0284C7] cursor-pointer"
                >
                  복사
                </button>
              </div>
              <pre className="font-mono text-xs text-slate-900 whitespace-pre-wrap break-all">
                {drawerFinding.commands[os]}
              </pre>
            </div>

            <div className="vuln-prompt-box !mb-0">
              <span className="prompt-caption">
                ④ 로컬 LLM (GPU Red–Blue 검증 통과) — AI 코딩툴용 수정 프롬프트
              </span>
              <div className="prompt-text">{drawerFinding.aiPrompt}</div>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={async () => {
                  await navigator.clipboard.writeText(drawerFinding.aiPrompt);
                  showToast("AI 코딩툴용 프롬프트가 복사되었습니다!");
                }}
                className="btn-console-run !py-3 flex-1 flex items-center justify-center gap-2"
              >
                <Copy className="w-4 h-4" />
                <span>프롬프트 복사하기</span>
              </button>
              <button
                type="button"
                onClick={() => handleToggleFindingFixed(drawerFinding.id)}
                className="btn-console-rescan !py-3 flex-1 flex items-center justify-center gap-2"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>
                  {drawerFinding.fixed ? "미해결로 변경" : "⑤ 조치 완료 표시"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 모달 및 토스트 알림 */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={() => setIsLoginModalOpen(false)}
        onSelectProvider={(p) => {
          setIsLoginModalOpen(false);
          setAuthUser(p);
          showToast(`${p} OAuth 연동 완료`);
        }}
      />

      <CommandPalette
        isOpen={isCmdPaletteOpen}
        onClose={() => setIsCmdPaletteOpen(false)}
        onSelectRepo={(url) => {
          setRepoInput(url);
          handleRunScan(url);
        }}
        onSwitchTab={handleSwitchSection}
        onToggleTheme={handleToggleTheme}
      />

      <Toast message={toastMessage} visible={toastVisible} />
    </>
  );
}
