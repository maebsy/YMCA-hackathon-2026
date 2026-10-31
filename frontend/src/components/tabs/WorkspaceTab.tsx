"use client";

import React, { useState } from "react";
import {
  Play,
  RotateCw,
  Copy,
  Sparkles,
  Flame,
  Check,
  AlertTriangle,
} from "lucide-react";
import { Finding, LogItem, OS, Hosting } from "@/types/security";

interface WorkspaceTabProps {
  findings: Finding[];
  onToggleFindingFixed: (id: string) => void;
  selectedFindingId: string;
  onSelectFindingId: (id: string) => void;
  logs: LogItem[];
  onRunScan: (repoUrl: string) => void;
  isScanning: boolean;
  hasRealScan: boolean;
  os: OS;
  onChangeOS: (os: OS) => void;
  hosting: Hosting;
  onChangeHosting: (host: Hosting) => void;
  countdown: string;
  onShowToast: (msg: string) => void;
  repoInput: string;
  onChangeRepoInput: (val: string) => void;
}

export const WorkspaceTab: React.FC<WorkspaceTabProps> = ({
  findings,
  onToggleFindingFixed,
  selectedFindingId,
  onSelectFindingId,
  logs,
  onRunScan,
  isScanning,
  hasRealScan,
  os,
  onChangeOS,
  hosting,
  onChangeHosting,
  countdown,
  onShowToast,
  repoInput,
  onChangeRepoInput,
}) => {
  const [repoError, setRepoError] = useState(false);

  const selectedFinding =
    findings.find((f) => f.id === selectedFindingId) || findings[0];

  const handleScanSubmit = () => {
    const regex = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/;
    if (!regex.test(repoInput.trim())) {
      setRepoError(true);
      return;
    }
    setRepoError(false);
    onRunScan(repoInput.trim());
  };

  const copyToClipboard = async (text: string, msg: string) => {
    try {
      await navigator.clipboard.writeText(text);
      onShowToast(msg);
    } catch {
      onShowToast("복사에 실패했습니다. 클립보드 권한을 확인하거나 내용을 직접 선택해 복사해 주세요.");
    }
  };

  const actCount = findings.filter((f) => !f.fixed && f.decision === "act").length;
  const attendCount = findings.filter((f) => !f.fixed && f.decision === "attend").length;
  const trackCount = findings.filter((f) => !f.fixed && f.decision === "trackstar").length;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Hero 섹션 */}
      <section className="border-b border-[#27272a] pb-8">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-2 font-mono text-xs text-[#d4ff3a] uppercase tracking-widest mb-3">
              <span>{"// VIBE CODER SECURITY PLATFORM"}</span>
              <span className="text-[#27272a]">•</span>
              <span>ZERO-RETENTION SOURCE SCAN</span>
            </div>
            <h1 className="font-mono text-3xl sm:text-5xl font-bold tracking-tight leading-tight">
              찾고, 고치고,{" "}
              <span className="text-[#d4ff3a] underline decoration-2 underline-offset-8">
                72시간
              </span>{" "}
              안에 끝냅니다.
            </h1>
            <p className="text-[#a1a1aa] mt-4 max-w-2xl text-base leading-relaxed">
              바이브코더와 비개발자도 즉시 다음 행동이 보이는 웹사이트 보안 서비스.
              Opengrep·OSV·Gitleaks 및 자체 특화 룰셋으로 진단하고, 로컬 GPU LLM의{" "}
              <strong className="text-white font-medium">Red–Blue 검증 루프</strong>를
              결과와 수정 지시를 확인하고 AI 코딩툴에 전달할 수 있습니다.
            </p>
          </div>

          {/* 5단계 파이프라인 인디케이터 */}
          <div className="bg-[#111113] border border-[#27272a] rounded-xl p-4 font-mono text-xs shrink-0">
            <div className="text-[#a1a1aa] mb-2.5 flex items-center justify-between">
              <span>MVP 5-STEP PIPELINE</span>
              <span className="text-[#d4ff3a]">④ AI 수정 지시</span>
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="step-pill done">① 권한</span>
              <span className="text-[#27272a]">→</span>
              <span className="step-pill done">② 로컬검사</span>
              <span className="text-[#27272a]">→</span>
              <span className="step-pill done">③ 알림</span>
              <span className="text-[#27272a]">→</span>
              <span className="step-pill hl">④ 대응(MCP)</span>
              <span className="text-[#27272a]">→</span>
              <span className="step-pill">⑤ 재검사·리포트</span>
            </div>
          </div>
        </div>
      </section>

      {/* 1. 저장소 입력 & 골든타임 타이머 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* 새 검사 입력 패널 */}
        <div className="lg:col-span-8 bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden flex flex-col justify-between">
          <div className="chrome-bar">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              72hours.app/new — Repository & Environment
            </span>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <label
                htmlFor="repoInput"
                className="font-mono text-sm font-bold flex items-center gap-2"
              >
                <span className="text-[#d4ff3a]">$</span> 검사할 GitHub 저장소
              </label>
              <span className="font-mono text-xs text-[#a1a1aa] hidden sm:inline">
                읽기 전용 수집 · 검사 직후 코드 즉시 삭제
              </span>
            </div>

            <div className="flex flex-col sm:flex-row gap-2.5">
              <input
                id="repoInput"
                type="text"
                value={repoInput}
                onChange={(e) => {
                  onChangeRepoInput(e.target.value);
                  setRepoError(false);
                }}
                className="flex-1 font-mono text-sm px-4 py-3 rounded-lg bg-[#0a0a0a] border border-[#27272a] text-white focus:outline-none focus:border-[#d4ff3a] transition"
                placeholder="https://github.com/owner/repo"
              />
              <button
                onClick={handleScanSubmit}
                disabled={isScanning}
                className="px-5 py-3 rounded-lg bg-[#d4ff3a] text-[#0a0a0a] font-mono text-sm font-bold hover:brightness-110 transition flex items-center justify-center gap-2 shrink-0 cursor-pointer disabled:opacity-50"
              >
                <Play className="w-4 h-4 fill-current" />
                <span>{isScanning ? "검사 중..." : "검사 시작 ⏎"}</span>
              </button>
            </div>
            {repoError && (
              <p className="font-mono text-xs text-[#ff5f56] flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                github.com/소유자/저장소 형식으로 입력해 주세요 (예:
                https://github.com/minji-cafe/order-site)
              </p>
            )}

            {/* 환경 선택 칩 */}
            <div className="pt-2 flex flex-wrap items-center gap-y-3 gap-x-6 font-mono text-xs border-t border-[#27272a]/60">
              <div className="flex items-center gap-2">
                <span className="text-[#a1a1aa]">사용 OS:</span>
                <button
                  onClick={() => onChangeOS("windows")}
                  className={`os-chip ${os === "windows" ? "active-chip" : ""}`}
                >
                  Windows
                </button>
                <button
                  onClick={() => onChangeOS("macos")}
                  className={`os-chip ${os === "macos" ? "active-chip" : ""}`}
                >
                  macOS
                </button>
                <button
                  onClick={() => onChangeOS("linux")}
                  className={`os-chip ${os === "linux" ? "active-chip" : ""}`}
                >
                  Linux
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#a1a1aa]">배포 환경:</span>
                <button
                  onClick={() => onChangeHosting("vercel")}
                  className={`host-chip ${hosting === "vercel" ? "active-chip" : ""}`}
                >
                  Vercel
                </button>
                <button
                  onClick={() => onChangeHosting("netlify")}
                  className={`host-chip ${hosting === "netlify" ? "active-chip" : ""}`}
                >
                  Netlify
                </button>
                <button
                  onClick={() => onChangeHosting("unknown")}
                  className={`host-chip ${hosting === "unknown" ? "active-chip" : ""}`}
                >
                  모름
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 72시간 골든타임 타이머 & SSVC 요약 */}
        <div className="lg:col-span-4 bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden flex flex-col justify-between">
          <div className="chrome-bar justify-between">
            <div className="flex items-center gap-2">
              <div className="dots">
                <i />
                <i />
                <i />
              </div>
              <span className="font-mono text-xs text-[#a1a1aa] ml-2">
                SLA & Golden Time
              </span>
            </div>
            <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-[#ff9f43]/15 text-[#ff9f43] border border-[#ff9f43]/40">
              24h·48h 재알림 켜짐
            </span>
          </div>
          <div className="p-6 space-y-5">
            <div>
              <div className="font-mono text-xs text-[#a1a1aa] flex items-center justify-between">
                <span>72시간 해결 타이머 (발견 시점 기준)</span>
                <span className="text-[#ff9f43] font-bold">ACTIVE</span>
              </div>
              <div className="font-mono text-4xl font-bold text-[#ff9f43] tracking-tight mt-1 tabular-nums">
                {countdown}
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2 font-mono">
              <div className="p-2.5 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
                <span className="text-[11px] text-[#a1a1aa] block">지금 바로</span>
                <b className="text-xl text-[#ff5f56]">{actCount}</b>
              </div>
              <div className="p-2.5 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
                <span className="text-[11px] text-[#a1a1aa] block">이번 주</span>
                <b className="text-xl text-[#ff9f43]">{attendCount}</b>
              </div>
              <div className="p-2.5 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
                <span className="text-[11px] text-[#a1a1aa] block">지켜보기</span>
                <b className="text-xl text-[#ffd43b]">{trackCount}</b>
              </div>
              <div className="p-2.5 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
                <span className="text-[11px] text-[#a1a1aa] block">미검사</span>
                <b className="text-xl text-[#d4ff3a]">0</b>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. 실시간 터미널 보안 엔진 로그 */}
      <div className="bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="chrome-bar justify-between">
          <div className="flex items-center gap-2">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              72hours.app/scans/41 — Live Security Engine Output
            </span>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="text-[#d4ff3a] flex items-center gap-1.5">
              {isScanning ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-[#ff9f43] animate-ping" />
                  <span className="text-[#ff9f43]">SCANNING IN PROGRESS...</span>
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-[#d4ff3a]" />
                  <span>{hasRealScan ? `SCAN COMPLETE (${findings.length} Findings)` : "저장소를 입력하고 검사를 시작하세요"}</span>
                </>
              )}
            </span>
            <button
              onClick={() => onRunScan(repoInput)}
              disabled={isScanning || !hasRealScan}
              className="px-2.5 py-1 rounded bg-[#18181b] hover:bg-[#27272a] text-[#fafafa] border border-[#27272a] transition flex items-center gap-1 cursor-pointer disabled:opacity-50"
            >
              <RotateCw className={`w-3 h-3 ${isScanning ? "animate-spin" : ""}`} />
              <span>⑤ 재검사 실행</span>
            </button>
          </div>
        </div>
        <div className="p-5 bg-[#0a0a0a] font-mono text-xs sm:text-[13px] leading-relaxed overflow-x-auto space-y-1">
          {logs.map((l, idx) => (
            <div key={idx} className="flex items-center gap-3">
              <span className="text-[#71717a] select-none">{l.time}</span>
              <span className="text-[#a1a1aa] font-bold w-20 shrink-0">
                {l.step}
              </span>
              <span className="text-[#fafafa] flex-1">{l.msg}</span>
              <span
                className={`font-bold ${
                  l.type === "warn"
                    ? "text-[#ff9f43]"
                    : l.type === "ok"
                    ? "text-[#d4ff3a]"
                    : "text-[#a1a1aa]"
                }`}
              >
                {l.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 3. 취약점 목록 & 상세 2단 분할 뷰 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* 왼쪽: 취약점 목록 */}
        <div className="lg:col-span-5 bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden">
          <div className="chrome-bar justify-between">
            <span className="font-mono text-xs text-[#a1a1aa]">
              탐지된 취약점 목록 (SSVC 우선순위)
            </span>
            <span className="font-mono text-[11px] text-[#a1a1aa]">
              클릭하여 조치 가이드 확인
            </span>
          </div>
          <div className="divide-y divide-[#27272a]">
            {findings.map((item) => {
              const isSel = item.id === selectedFindingId;
              let pillClass = "pill-attend";
              let pillText: string = item.decision;

              if (item.fixed) {
                pillClass = "pill-ok";
                pillText = "해결됨";
              } else if (item.decision === "act") {
                pillClass = "pill-act";
              } else if (item.decision === "trackstar") {
                pillClass = "pill-trackstar";
                pillText = "track*";
              }

              const verdictColor = item.fixed
                ? "border-[#d4ff3a]/50 text-[#d4ff3a]"
                : item.verdictType === "warn"
                ? "border-[#ff5f56]/50 text-[#ff5f56]"
                : "border-[#27272a] text-[#a1a1aa]";

              return (
                <div
                  key={item.id}
                  onClick={() => onSelectFindingId(item.id)}
                  className={`finding-row p-4 flex items-center justify-between gap-3 ${
                    isSel ? "selected" : ""
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`${pillClass} w-16 text-center shrink-0`}>
                      {pillText}
                    </span>
                    <div className="min-w-0">
                      <div
                        className={`text-sm font-medium text-white truncate ${
                          item.fixed ? "line-through text-[#a1a1aa]" : ""
                        }`}
                      >
                        {item.title}
                      </div>
                      <small className="font-mono text-xs text-[#a1a1aa] block truncate">
                        {item.file}
                      </small>
                    </div>
                  </div>
                  <span
                    className={`font-mono text-[11px] px-2 py-0.5 rounded border shrink-0 ${verdictColor}`}
                  >
                    {item.fixed ? "검증 통과" : item.verdict}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 오른쪽: 선택한 취약점 상세 가이드 */}
        {selectedFinding && (
          <div className="lg:col-span-7 bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden sticky top-20">
            <div className="chrome-bar justify-between">
              <div className="flex items-center gap-2">
                <div className="dots">
                  <i />
                  <i />
                  <i />
                </div>
                <span className="font-mono text-xs text-[#a1a1aa] ml-2">
                  72hours.app/scans/41/findings/{selectedFinding.id}
                </span>
              </div>
              <button
                onClick={() => onToggleFindingFixed(selectedFinding.id)}
                disabled={isScanning}
                className={`px-2.5 py-1 rounded font-mono text-xs transition cursor-pointer flex items-center gap-1 ${
                  selectedFinding.fixed
                    ? "bg-[#27272a] text-[#a1a1aa] hover:text-white"
                    : "bg-[#d4ff3a]/15 text-[#d4ff3a] border border-[#d4ff3a]/40 hover:bg-[#d4ff3a] hover:text-black"
                }`}
              >
                <Check className="w-3.5 h-3.5" />
                <span>
                  {hasRealScan ? "조치 후 실제 재검사" : selectedFinding.fixed
                    ? "↺ 미해결 상태로 되돌리기"
                    : "✓ 조치 완료 및 재검사 검증"}
                </span>
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* 상단 메타 배지 */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={
                      selectedFinding.fixed
                        ? "pill-ok"
                        : selectedFinding.decision === "act"
                        ? "pill-act"
                        : selectedFinding.decision === "attend"
                        ? "pill-attend"
                        : "pill-trackstar"
                    }
                  >
                    {selectedFinding.fixed
                      ? "해결 · 재검사 통과"
                      : selectedFinding.decisionLabel}
                  </span>
                  <span className="font-mono text-xs text-[#a1a1aa] border border-[#27272a] rounded px-2 py-0.5">
                    {selectedFinding.scope}
                  </span>
                  <span className="font-mono text-xs text-[#a1a1aa] border border-[#27272a] rounded px-2 py-0.5">
                    {selectedFinding.confidence}
                  </span>
                  <span
                    className={`font-mono text-xs border rounded px-2 py-0.5 ${
                      selectedFinding.verdictType === "warn"
                        ? "text-[#ff5f56] border-[#ff5f56]/40"
                        : "text-[#d4ff3a] border-[#d4ff3a]/40"
                    }`}
                  >
                    LLM: {selectedFinding.verdict}
                  </span>
                </div>
                <span className="font-mono text-xs text-[#a1a1aa] bg-[#0a0a0a] px-2.5 py-1 rounded border border-[#27272a]">
                  {selectedFinding.file}
                </span>
              </div>

              {/* 제목 및 비개발자 설명 */}
              <div>
                <h2 className="font-mono text-xl font-bold text-white mb-2">
                  {selectedFinding.title}
                </h2>
                <p className="text-[#fafafa] text-sm leading-relaxed">
                  {selectedFinding.desc}
                </p>
              </div>

              {/* Red Team 공격 시나리오 경고 박스 */}
              <div className="p-4 rounded-lg bg-[#ff5f56]/10 border border-[#ff5f56]/30 space-y-1.5">
                <div className="font-mono text-xs font-bold text-[#ff5f56] flex items-center gap-1.5">
                  <Flame className="w-4 h-4" />
                  <span>RED TEAM 공격 시나리오 (악용 시 피해)</span>
                </div>
                <p className="text-xs sm:text-sm text-[#fafafa]/90 leading-relaxed">
                  {selectedFinding.redScenario}
                </p>
              </div>

              {/* 왜 지금인가 & 내 OS 맞춤 명령 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] flex flex-col justify-between space-y-3">
                  <div>
                    <span className="font-mono text-[11px] text-[#d4ff3a] uppercase tracking-wider block mb-2">
                      왜 지금인가 (CISA SSVC)
                    </span>
                    <ul className="text-xs sm:text-sm space-y-2 text-[#fafafa] list-disc pl-4">
                      {selectedFinding.why.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                  <span className="font-mono text-[11px] text-[#a1a1aa] pt-2 border-t border-[#27272a]">
                    risk.factors[].reason
                  </span>
                </div>

                <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] flex flex-col justify-between space-y-3">
                  <div className="space-y-2.5">
                    <span className="font-mono text-[11px] text-[#d4ff3a] uppercase tracking-wider">
                      이렇게 고치세요 (터미널 명령)
                    </span>
                    {/* OS 탭 */}
                    <div className="flex border-b border-[#27272a] font-mono text-xs">
                      <button
                        onClick={() => onChangeOS("windows")}
                        className={`px-2.5 py-1.5 border-b-2 cursor-pointer ${
                          os === "windows"
                            ? "border-[#d4ff3a] text-white"
                            : "border-transparent text-[#a1a1aa]"
                        }`}
                      >
                        Windows
                      </button>
                      <button
                        onClick={() => onChangeOS("macos")}
                        className={`px-2.5 py-1.5 border-b-2 cursor-pointer ${
                          os === "macos"
                            ? "border-[#d4ff3a] text-white"
                            : "border-transparent text-[#a1a1aa]"
                        }`}
                      >
                        macOS
                      </button>
                      <button
                        onClick={() => onChangeOS("linux")}
                        className={`px-2.5 py-1.5 border-b-2 cursor-pointer ${
                          os === "linux"
                            ? "border-[#d4ff3a] text-white"
                            : "border-transparent text-[#a1a1aa]"
                        }`}
                      >
                        Linux
                      </button>
                    </div>
                    <pre className="p-3 rounded bg-[#111113] border border-[#27272a] font-mono text-xs text-[#d4ff3a] overflow-x-auto whitespace-pre-wrap break-all">
                      {selectedFinding.commands[os]}
                    </pre>
                    <button
                      onClick={() =>
                        copyToClipboard(
                          selectedFinding.commands[os],
                          `${os.toUpperCase()} 터미널 명령어가 복사되었습니다.`
                        )
                      }
                      className="w-full py-1.5 rounded bg-[#18181b] hover:bg-[#27272a] border border-[#27272a] font-mono text-xs text-[#fafafa] transition flex items-center justify-center gap-1.5 cursor-pointer"
                    >
                      <Copy className="w-3.5 h-3.5" /> 명령어 복사
                    </button>
                  </div>
                  <span className="font-mono text-[11px] text-[#a1a1aa]">
                    guide.actions[].commands[os={os}].lines · hosting={hosting}
                  </span>
                </div>
              </div>

              {/* ④ 대응 안내: AI 코딩툴 (MCP / 프롬프트) 전달 블록 */}
              <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#d4ff3a]/40 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-[#d4ff3a] text-black font-mono text-[11px] font-bold">
                      ④ MCP 연동
                    </span>
                    <span className="font-mono text-xs font-bold text-white">
                      Cursor · Claude Code · Codex 수정 지시문
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-[#a1a1aa]">
                    코드 원문 미포함 (파일·줄·규칙 ID만 전달)
                  </span>
                </div>
                <pre className="p-3 rounded bg-[#111113] border border-[#27272a] font-mono text-xs text-[#fafafa] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  {selectedFinding.aiPrompt}
                </pre>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-[#a1a1aa]">
                    MCP 도구: <code>list_findings</code>, <code>get_fix_task</code>
                  </span>
                  <button
                    onClick={() =>
                      copyToClipboard(
                        selectedFinding.aiPrompt,
                        "AI 코딩툴(Cursor/Claude Code)용 수정 지시문이 복사되었습니다."
                      )
                    }
                    className="px-4 py-2 rounded bg-[#d4ff3a] text-black font-mono text-xs font-bold hover:brightness-110 transition flex items-center gap-1.5 cursor-pointer"
                  >
                    <Sparkles className="w-3.5 h-3.5" /> AI 코딩툴에 지시문 복사
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
