"use client";

import React, { useState, useEffect } from "react";
import { Header } from "@/components/Header";
import { Toast } from "@/components/Toast";
import { LoginModal } from "@/components/LoginModal";
import { CommandPalette } from "@/components/CommandPalette";
import { WorkspaceTab } from "@/components/tabs/WorkspaceTab";
import { ArchitectureTab } from "@/components/tabs/ArchitectureTab";
import { IncidentTab } from "@/components/tabs/IncidentTab";
import { ReportTab } from "@/components/tabs/ReportTab";
import { initialFindings, defaultLogs } from "@/data/mockData";
import { TabType, OS, Hosting, Finding, LogItem } from "@/types/security";
import { startScan, llmHealthy, explain, itemToFinding, mergeExplanation, now, saveLast, loadLast } from "@/lib/api";
/* eslint-disable @typescript-eslint/no-explicit-any */

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("workspace");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [selectedFindingId, setSelectedFindingId] = useState<string>("s1");
  const [logs, setLogs] = useState<LogItem[]>(defaultLogs);
  const [isScanning, setIsScanning] = useState(false);
  // 실제 검사 상태: 직전 엔진 결과(재검사 비교용), 리포트 입력(scan·findings·explain_results)
  const [lastResult, setLastResult] = useState<any>(null);
  const [reportInput, setReportInput] = useState<any>(null);

  const [os, setOs] = useState<OS>("windows");
  const [hosting, setHosting] = useState<Hosting>("vercel");
  const [repoInput, setRepoInput] = useState(
    "https://github.com/minji-cafe/order-site"
  );
  const [authUser, setAuthUser] = useState("minji-cafe 연결됨");
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isCmdPaletteOpen, setIsCmdPaletteOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const [toastVisible, setToastVisible] = useState(false);

  // 새로고침해도 마지막 실제 검사 결과를 되살립니다 (브라우저 보관)
  useEffect(() => {
    const saved = loadLast<any>();
    if (!saved?.findings?.length) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFindings(saved.findings);
    setSelectedFindingId(saved.findings[0].id);
    setLastResult(saved.result ?? null);
    setReportInput(saved.reportInput ?? null);
    if (saved.repoUrl) setRepoInput(saved.repoUrl);
    if (saved.logs) setLogs(saved.logs);
  }, []);

  // 72시간 실시간 카운트다운 타이머
  const [remainingSeconds, setRemainingSeconds] = useState(
    61 * 3600 + 12 * 60 + 40
  );

  // 실제 검사 결과가 있으면 72시간 타이머를 첫 발견 시각(detected_at) 기준으로 맞춥니다
  useEffect(() => {
    const scan = reportInput?.scan;
    if (!scan?.detected_at) return;
    const deadline = new Date(scan.detected_at).getTime() + 72 * 3600 * 1000;
    const left = scan.resolved_at ? 0 : Math.max(0, Math.floor((deadline - Date.now()) / 1000));
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
    const m = String(Math.floor((remainingSeconds % 3600) / 60)).padStart(2, "0");
    const s = String(remainingSeconds % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setToastVisible(true);
    setTimeout(() => {
      setToastVisible(false);
    }, 2400);
  };

  const handleToggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    showToast(
      newTheme === "dark"
        ? "다크 모드(#0a0a0a)로 전환되었습니다."
        : "라이트 모드(#fafafa)로 전환되었습니다."
    );
  };

  // 전역 단축키 (⌘K / Ctrl+K, ESC)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsCmdPaletteOpen(true);
      } else if (e.key === "Escape") {
        setIsCmdPaletteOpen(false);
        setIsLoginModalOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // 실제 검사: /api/scans(보안엔진) → /api/llm/explain(GPU Red–Blue)
  const handleRunScan = async (url: string) => {
    setIsScanning(true);
    const log = (step: string, msg: string, status: string, type: "ok" | "warn" = "ok") =>
      setLogs((prev) => [...prev, { time: now(), step, msg, status, type }]);
    setLogs([]);
    const prev = lastResult?.target?.repo_url === url ? lastResult : null;
    log("clone   ", `${url.replace("https://github.com/", "")} ${prev ? "재검사" : "검사"} 중 (OSV·Opengrep·Gitleaks·설정 검사)...`, "…");
    const collected: LogItem[] = [];
    const log2 = (step: string, msg: string, status: string, type: "ok" | "warn" = "ok") => {
      collected.push({ time: now(), step, msg, status, type });
      log(step, msg, status, type);
    };
    try {
      const data = await startScan(url, prev);
      for (const [tool, c] of Object.entries<any>(data.coverage)) {
        log2(tool.padEnd(8), `${c.engine || tool} ${c.status}${c.message ? " · " + c.message.slice(0, 80) : ""}`,
          `${c.count}건`, c.status === "ok" || c.status === "skipped" ? "ok" : "warn");
      }
      log2("cleanup ", "검사한 소스 코드 임시 폴더 삭제", "✓ 삭제됨");
      if (data.comparison) {
        const c = data.comparison;
        log2("rescan  ", `새로 ${c.new ?? 0} · 계속 ${c.persisting ?? 0} · 해결 ${c.resolved ?? 0} · 확인불가 ${c.unverifiable ?? 0}`,
          (c.new ?? 0) === 0 && (c.persisting ?? 0) === 0 ? "✓ 통과" : "! 남은 문제", (c.new ?? 0) + (c.persisting ?? 0) ? "warn" : "ok");
      }
      let mapped: Finding[] = (data.llm_input?.items || []).map(itemToFinding);
      let explainResults: any[] = [];
      const rInput = { scan: data.report_scan, findings: data.findings || [], explain_results: explainResults };
      const persist = () => saveLast({ repoUrl: url, findings: mapped, result: data.result,
        reportInput: { ...rInput, explain_results: explainResults }, logs: collected });
      setFindings(mapped);
      setLastResult(data.result);
      setReportInput(rInput);
      if (mapped[0]) setSelectedFindingId(mapped[0].id);
      persist();
      showToast(`${prev ? "재검사" : "검사"} 완료: ${mapped.length}건 (${data.duration_sec}초)`);

      if (!data.findings?.length) return;
      if (!(await llmHealthy())) {
        log2("gpu-llm ", "GPU LLM 서버에 연결할 수 없어 엔진 결과만 표시합니다", "! 연결 안 됨", "warn");
        persist();
        return;
      }
      log("gpu-llm ", "Red–Blue 해석 중 (상위 5건)...", "…");
      const open = (data.findings as any[]).filter((f) => f.status !== "code_resolved");
      explainResults = await explain(open.slice(0, 5), os);
      const byFp = new Map<string, any>();
      for (const r of explainResults) for (const fp of [r.fingerprint, ...(r.covers || [])]) byFp.set(fp, r);
      mapped = mapped.map((f) => (byFp.has(f.id) ? mergeExplanation(f, byFp.get(f.id)) : f));
      setFindings(mapped);
      setReportInput({ ...rInput, explain_results: explainResults });
      log2("gpu-llm ", "Red–Blue 해석 완료", `✓ ${explainResults.filter((r) => r.status === "done").length}건`);
      persist();
    } catch (e: any) {
      log("error   ", String(e?.message || e), "✗ 실패", "warn");
      showToast(`검사 실패: ${e?.message || e}`);
    } finally {
      setIsScanning(false);
    }
  };

  const handleToggleFindingFixed = (id: string) => {
    setFindings((prev) =>
      prev.map((f) => {
        if (f.id === id) {
          const nextFixed = !f.fixed;
          showToast(
            nextFixed
              ? `[${f.id}] 재검사 통과! 취약점이 해결 처리되었습니다.`
              : `[${f.id}] 미해결 상태로 변경되었습니다.`
          );
          return { ...f, fixed: nextFixed };
        }
        return f;
      })
    );
  };

  const handleSelectProvider = (provider: string) => {
    setIsLoginModalOpen(false);
    setAuthUser(`${provider} 인증됨`);
    showToast(
      `Supabase Auth (${provider}) 완료! Bearer 토큰이 API 헤더에 연결되었습니다.`
    );
  };

  return (
    <div className="min-h-screen relative overflow-x-hidden">
      {/* 배경 그리드 & 오로라 글로우 */}
      <div className="bg-grid fixed inset-0 pointer-events-none z-0" />
      <div className="glow-orb fixed -top-40 left-1/2 -translate-x-1/2 w-[700px] h-[350px] rounded-full pointer-events-none z-0" />

      {/* 상단 네비게이션 헤더 */}
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onOpenCmdPalette={() => setIsCmdPaletteOpen(true)}
        onOpenLoginModal={() => setIsLoginModalOpen(true)}
        authUser={authUser}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      {/* 메인 콘텐츠 영역 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-10 relative z-10">
        <p className="mb-6 rounded-lg border border-[#ff9f43]/50 bg-[#ff9f43]/10 p-3 font-mono text-xs text-[#ff9f43]">
          실제 연결 · 검사·재검사는 보안엔진(/api/scans)과 GPU LLM(/api/llm/explain)을, 리포트 탭의 「실제 검사 리포트」는 /api/reports/plain을 호출합니다. 로그인·공격 재현·예제 리포트는 아직 예제입니다.
          실제 인증·보안 검증을 수행하지 않으며, 리포트를 실제 증빙으로 사용할 수 없습니다.
        </p>
        {activeTab === "workspace" && (
          <WorkspaceTab
            findings={findings}
            onToggleFindingFixed={handleToggleFindingFixed}
            selectedFindingId={selectedFindingId}
            onSelectFindingId={setSelectedFindingId}
            logs={logs}
            onRunScan={handleRunScan}
            isScanning={isScanning}
            os={os}
            onChangeOS={setOs}
            hosting={hosting}
            onChangeHosting={setHosting}
            countdown={formatCountdown()}
            onShowToast={showToast}
            repoInput={repoInput}
            onChangeRepoInput={setRepoInput}
          />
        )}

        {activeTab === "architecture" && <ArchitectureTab />}

        <div hidden={activeTab !== "incident"}>
          <IncidentTab onShowToast={showToast} />
        </div>

        {activeTab === "report" && (
          <ReportTab
            reportInput={reportInput}
            onShowToast={showToast}
            onOpenLoginModal={() => setIsLoginModalOpen(true)}
          />
        )}
      </main>

      {/* 모달 및 알림 */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={() => setIsLoginModalOpen(false)}
        onSelectProvider={handleSelectProvider}
      />

      <CommandPalette
        isOpen={isCmdPaletteOpen}
        onClose={() => setIsCmdPaletteOpen(false)}
        onSelectRepo={(url) => {
          setRepoInput(url);
          handleRunScan(url);
        }}
        onSwitchTab={setActiveTab}
        onToggleTheme={handleToggleTheme}
      />

      <Toast message={toastMessage} visible={toastVisible} />
    </div>
  );
}
