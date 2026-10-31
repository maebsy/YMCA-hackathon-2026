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
import { Finding, LogItem, OS } from "@/types/security";

// 실검증(/verify)이 실제 공격으로 재현해 보여 주는 종류 (lib/api.ts의 RUNTIME_VERIFIABLE_CWE와 같게 유지)
const RUNTIME_VERIFIABLE_CWE = new Set(["CWE-89", "CWE-79", "CWE-78", "CWE-77"]);
import { McpHandoff } from "@/components/McpHandoff";

interface WorkspaceTabProps {
  compact?: boolean;
  hasResult?: boolean;
  pendingIds?: string[];
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
  countdown,
  onShowToast,
  repoInput,
  onChangeRepoInput,
  compact = false,
  hasResult = true,
  pendingIds = [],
}) => {
  const [repoError, setRepoError] = useState(false);

  const selectedFinding =
    findings.find((f) => f.id === selectedFindingId) || findings[0];

  const handleScanSubmit = () => {
    const trimmed = repoInput.trim();
    const normalized = /^github\.com\//i.test(trimmed) ? `https://${trimmed}` : trimmed;
    const regex = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/;
    if (!regex.test(normalized)) {
      setRepoError(true);
      return;
    }
    setRepoError(false);
    if (normalized !== repoInput) onChangeRepoInput(normalized);
    onRunScan(normalized);
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
      {!compact && <><section className="border-b border-[#27272a] pb-8">
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

      </>}
      {/* 2. 실시간 터미널 보안 엔진 로그 */}
      {!compact && <div className="bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="chrome-bar justify-between">
          <div className="flex items-center gap-2">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              {compact ? "검사 진행 기록" : "72hours.app/scans/41 — Live Security Engine Output"}
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
                  <span>{hasResult ? `검사 결과 ${findings.length}건` : "아직 검사하지 않았어요"}</span>
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
          {logs.length === 0 && <p className="text-[#a1a1aa]">검사를 시작하면 실제 엔진 진행 기록이 표시됩니다.</p>}
          {logs.map((l, idx) => (
            <div key={idx} className="scan-log-row flex items-center gap-3">
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
      </div>}
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
            {findings.length === 0 && <p className="p-5 text-sm text-[#a1a1aa]">{hasResult ? "반환된 항목이 없습니다. 검사 범위와 도구 상태를 함께 확인하세요. 안전을 보증하는 결과가 아닙니다." : "GitHub 저장소를 검사하면 이곳에서 항목을 선택할 수 있어요."}</p>}
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
                <button
                  type="button"
                  aria-pressed={isSel}
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
                    {item.fixed ? "엔진 검증 완료" : pendingIds.includes(item.id) ? "재검증 대기" : item.verdict}
                  </span>
                </button>
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
                  {compact ? `항목 ${selectedFinding.id}` : `72hours.app/scans/41/findings/${selectedFinding.id}`}
                </span>
              </div>
              <button
                onClick={() => onToggleFindingFixed(selectedFinding.id)}
                disabled={isScanning || (compact && selectedFinding.fixed)}
                className={`px-2.5 py-1 rounded font-mono text-xs transition cursor-pointer flex items-center gap-1 ${
                  selectedFinding.fixed
                    ? "bg-[#27272a] text-[#a1a1aa] hover:text-white"
                    : "bg-[#d4ff3a]/15 text-[#d4ff3a] border border-[#d4ff3a]/40 hover:bg-[#d4ff3a] hover:text-black"
                }`}
              >
                <Check className="w-3.5 h-3.5" />
                <span>
                  {compact ? selectedFinding.fixed ? "엔진 검증 완료" : pendingIds.includes(selectedFinding.id) ? "조치 표시 취소" : "조치함 · 재검증 대기" : hasRealScan ? "조치 후 실제 재검사" : selectedFinding.fixed
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
                      ? compact ? "코드 해결 확인" : "해결 · 재검사 통과"
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
                    {compact ? selectedFinding.verdict : `LLM: ${selectedFinding.verdict}`}
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
                  <span>{compact ? "위험 설명 · 추가 AI 해석" : "RED TEAM 공격 시나리오 (악용 시 피해)"}</span>
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
                    {compact ? "엔진의 근거와 안내를 함께 검토하세요." : "risk.factors[].reason"}
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
                      {selectedFinding.commands[os] || (compact ? "터미널 명령 없이 코드를 고치는 항목입니다. 아래 'AI 수정 요청'을 코딩 도구에 붙여 넣어 고치세요." : "")}
                    </pre>
                    <button
                      disabled={compact && !selectedFinding.commands[os].trim()}
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
                    표시 OS: {os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux"} · 보기 설정은 서버로 보내지 않습니다.
                  </span>
                </div>
              </div>

              {/* ④ 대응 안내: AI 코딩툴 (MCP / 프롬프트) 전달 블록 */}
              <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#d4ff3a]/40 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-[#d4ff3a] text-black font-mono text-[11px] font-bold">
                      {compact ? "AI 수정 요청" : "④ MCP 연동"}
                    </span>
                    <span className="font-mono text-xs font-bold text-white">
                      Cursor · Claude Code · Codex 수정 지시문
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-[#a1a1aa]">
                    {compact ? "적용 전 내용을 검토하세요. 명령은 실행되지 않습니다." : "코드 원문 미포함 (파일·줄·규칙 ID만 전달)"}
                  </span>
                </div>
                <pre className="p-3 rounded bg-[#111113] border border-[#27272a] font-mono text-xs text-[#fafafa] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  {selectedFinding.aiPrompt}
                </pre>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-[#a1a1aa]">
                    {compact ? "복사 후 코딩 도구에 직접 전달하거나 아래 MCP 연결을 사용하세요." : <>MCP 도구: <code>list_findings</code>, <code>get_fix_prompt</code> · 프롬프트: <code>fix_finding</code></>}
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
                {compact && selectedFinding.cwe && RUNTIME_VERIFIABLE_CWE.has(selectedFinding.cwe) && !selectedFinding.fixed && (
                  <div className="p-3 rounded bg-[#111113] border border-[#27272a] flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-[#fafafa]/90">
                      고친 코드가 이 공격({selectedFinding.cwe})을 실제로 막는지 격리 환경에서 수정 전·후를 실행해 확인합니다. 지금은 데모 과녁으로 같은 종류의 공격을 재현합니다.
                    </span>
                    <a href="/verify?run=reference" className="px-3 py-1.5 rounded border border-[#d4ff3a] text-[#d4ff3a] font-mono text-xs font-bold hover:bg-[#d4ff3a]/10 transition">
                      실검증으로 확인하기 →
                    </a>
                  </div>
                )}
                <McpHandoff os={os} onShowToast={onShowToast} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
