"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { explain, itemToFinding, llmHealthy, loadLast, mergeExplanation, now, saveLast, startScan } from "@/lib/api";
import type { Finding, Hosting, LogItem, OS } from "@/types/security";

type JsonRecord = Record<string, unknown>;
type ReportInput = { scan: JsonRecord; findings: unknown[]; explain_results: JsonRecord[] };
type SavedRepository = { verificationSource: "engine-status-v1"; repoUrl: string; findings: Finding[]; result: JsonRecord; reportInput: ReportInput; logs: LogItem[]; pendingIds: string[] };
type RepositoryState = {
  repoInput: string; resultRepo: string; findings: Finding[]; result: JsonRecord | null;
  reportInput: ReportInput | null; logs: LogItem[]; pendingIds: string[]; selectedFindingId: string;
  isScanning: boolean; restored: boolean; error: string; message: string; os: OS; hosting: Hosting;
};
const initialState: RepositoryState = {
  repoInput: "", resultRepo: "", findings: [], result: null, reportInput: null, logs: [], pendingIds: [],
  selectedFindingId: "", isScanning: false, restored: false, error: "", message: "", os: "windows", hosting: "unknown",
};
function record(value: unknown): value is JsonRecord { return !!value && typeof value === "object" && !Array.isArray(value); }

/** A repository URL is deliberately separate from the website demo input. */
export function normalizeRepositoryUrl(value: string): string | null {
  const raw = value.trim();
  if (!/^https:\/\/github\.com\//i.test(raw) || /[%?#\\]/.test(raw)) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || url.hostname !== "github.com" || url.port || url.username || url.password) return null;
    const parts = url.pathname.replace(/\/$/, "").split("/");
    if (parts.length !== 3) return null;
    const [, owner, inputRepo] = parts;
    const repo = inputRepo.replace(/\.git$/, "");
    if (!/^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i.test(owner) || owner.includes("--")) return null;
    if (!/^[a-z\d_.-]{1,100}$/i.test(repo) || repo === "." || repo === "..") return null;
    return `https://github.com/${owner}/${repo}`;
  } catch { return null; }
}

function validFinding(value: unknown): value is Finding {
  if (!record(value) || !record(value.commands)) return false;
  const strings = ["id", "decisionLabel", "title", "file", "verdict", "confidence", "scope", "desc", "redScenario", "aiPrompt"];
  return strings.every(key => typeof value[key] === "string") && !!value.id &&
    ["act", "attend", "trackstar"].includes(String(value.decision)) && ["ok", "warn"].includes(String(value.verdictType)) &&
    typeof value.fixed === "boolean" && Array.isArray(value.why) && value.why.every(x => typeof x === "string") &&
    ["windows", "macos", "linux"].every(os => typeof (value.commands as JsonRecord)[os] === "string");
}

export function parseSavedRepository(value: unknown): SavedRepository | null {
  if (!record(value) || typeof value.repoUrl !== "string") return null;
  const repoUrl = normalizeRepositoryUrl(value.repoUrl);
  if (!repoUrl || !Array.isArray(value.findings) || !value.findings.every(validFinding) || !record(value.result) ||
    !record(value.reportInput) || !record(value.reportInput.scan) || !Array.isArray(value.reportInput.findings)) return null;
  const trustedVerification = value.verificationSource === "engine-status-v1";
  const legacyMarked = trustedVerification ? [] : value.findings.filter(finding => finding.fixed).map(finding => finding.id);
  const findings = trustedVerification ? value.findings : value.findings.map(finding => finding.fixed ? {
    ...finding, fixed: false, verdict: "과거 조치 표시 · 재검증 필요", verdictType: "warn" as const,
  } : finding);
  const logs: LogItem[] = Array.isArray(value.logs) ? value.logs.filter((item): item is LogItem => record(item) &&
    ["time", "step", "msg", "status"].every(key => typeof item[key] === "string") && (item.type === "ok" || item.type === "warn")) : [];
  const pendingIds = [...new Set([...(Array.isArray(value.pendingIds) ? value.pendingIds : []), ...legacyMarked]
    .filter((id): id is string => typeof id === "string" && findings.some(f => f.id === id && !f.fixed)))];
  return { verificationSource: "engine-status-v1", repoUrl, findings, result: value.result, reportInput: { scan: value.reportInput.scan, findings: value.reportInput.findings,
    explain_results: Array.isArray(value.reportInput.explain_results) ? value.reportInput.explain_results.filter(record) : [] }, logs, pendingIds };
}

type RepositoryContextValue = RepositoryState & {
  setRepoInput: (value: string) => void; setOS: (os: OS) => void; setHosting: (hosting: Hosting) => void;
  selectFinding: (id: string) => void; togglePending: (id: string) => void; showMessage: (message: string) => void;
  runScan: (url?: string) => Promise<void>;
};
const RepositoryContext = createContext<RepositoryContextValue | null>(null);

export function RepositoryProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<RepositoryState>(initialState);
  const busy = useRef(false);
  const operation = useRef(0);
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => {
    const lifecycle = operation;
    const saved = parseSavedRepository(loadLast<unknown>());
    // Browser storage is read after hydration; zero-finding results are valid too.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(current => saved ? { ...current, repoInput: saved.repoUrl, resultRepo: saved.repoUrl, findings: saved.findings,
      result: saved.result, reportInput: saved.reportInput, logs: saved.logs, pendingIds: saved.pendingIds,
      selectedFindingId: saved.findings[0]?.id ?? "", restored: true, message: "이 브라우저에 저장된 마지막 검사 결과를 불러왔습니다." } : { ...current, restored: true });
    return () => { lifecycle.current++; };
  }, []);
  function persist(current: RepositoryState) {
    if (current.result && current.reportInput && current.resultRepo) saveLast({ verificationSource: "engine-status-v1", repoUrl: current.resultRepo, findings: current.findings,
      result: current.result, reportInput: current.reportInput, logs: current.logs, pendingIds: current.pendingIds });
  }
  function change(update: (current: RepositoryState) => RepositoryState, save = false) {
    setState(current => {
      const next = update(current);
      if (save) persist(next);
      return next;
    });
  }
  async function runScan(input = stateRef.current.repoInput) {
    if (busy.current || !stateRef.current.restored) return;
    const normalized = normalizeRepositoryUrl(input);
    if (!normalized) {
      change(current => ({ ...current, error: "공개 GitHub 저장소의 HTTPS 주소를 입력하세요. 예: https://github.com/owner/repository" }));
      return;
    }
    const repoUrl = normalized;
    busy.current = true;
    const token = ++operation.current;
    const current = stateRef.current;
    const previous = current.resultRepo.toLowerCase() === repoUrl.toLowerCase() ? current.result : null;
    const selectedOS = current.os;
    const collected: LogItem[] = [];
    const active = () => operation.current === token;
    function log(step: string, msg: string, status: string, type: LogItem["type"] = "ok") {
      if (!active()) return;
      collected.push({ time: now(), step, msg, status, type });
      change(value => ({ ...value, logs: [...collected] }));
    }
    change(value => ({ ...value, repoInput: repoUrl, isScanning: true, error: "", message: "", logs: [] }));
    log("engine", `${repoUrl} ${previous ? "재검사" : "검사"}를 요청합니다.`, "접수 중");
    try {
      const data: unknown = await startScan(repoUrl, previous, status => log("status", `엔진 상태: ${status}`, "진행 중"));
      if (!active()) return;
      if (!record(data) || !record(data.result) || !record(data.report_scan) || !Array.isArray(data.findings) || !record(data.llm_input) || !Array.isArray(data.llm_input.items))
        throw new Error("엔진 응답에 검사 결과나 리포트 정보가 없습니다. 기존 결과를 유지합니다.");
      const items = data.llm_input.items;
      if (!items.every(record)) throw new Error("엔진 발견 항목의 형식이 올바르지 않습니다.");
      let mapped = items.map(item => ({ ...itemToFinding(item), redScenario: "추가 AI 해석이 아직 없습니다. 엔진 관찰 근거와 수정 안내를 직접 검토하세요." }));
      if (!mapped.every(validFinding)) throw new Error("엔진 발견 항목을 표시할 수 없습니다. 응답 형식을 확인하세요.");
      const result = data.result;
      const rawFindings = data.findings;
      let reportInput: ReportInput = { scan: data.report_scan, findings: rawFindings, explain_results: [] };
      if (record(data.coverage)) for (const [tool, coverage] of Object.entries(data.coverage)) {
        if (!record(coverage)) continue;
        log(tool, `${String(coverage.engine ?? tool)} · ${String(coverage.status ?? "상태 없음")}${coverage.message ? ` · ${String(coverage.message).slice(0, 160)}` : ""}`,
          `${typeof coverage.count === "number" ? coverage.count : "?"}건`, coverage.status === "ok" || coverage.status === "skipped" ? "ok" : "warn");
      }
      if (record(data.comparison)) log("rescan", `새 발견 ${data.comparison.new ?? 0} · 지속 ${data.comparison.persisting ?? 0} · 해결 ${data.comparison.resolved ?? 0} · 확인 불가 ${data.comparison.unverifiable ?? 0}`, "비교 결과");
      log("engine", `엔진 결과 ${mapped.length}건을 받았습니다. 검사 범위 밖의 안전을 보장하지 않습니다.`, "결과 수신");
      function publish(message: string) {
        if (!active()) return;
        change(value => ({ ...value, resultRepo: repoUrl, result, findings: mapped, reportInput, logs: [...collected],
          pendingIds: [], selectedFindingId: value.resultRepo.toLowerCase() === repoUrl.toLowerCase() && mapped.some(finding => finding.id === value.selectedFindingId)
            ? value.selectedFindingId : mapped[0]?.id ?? "", message }), true);
      }
      publish("엔진 검사가 끝났습니다. 아래 결과와 도구별 실행 범위를 확인하세요.");
      const open = rawFindings.filter(finding => record(finding) && finding.status !== "code_resolved");
      if (!open.length) return;
      try {
        if (!(await llmHealthy())) {
          log("LLM", "추가 해석 서버에 연결할 수 없어 엔진 결과와 기본 안내를 유지합니다.", "해석 없음", "warn");
          publish("엔진 결과를 표시합니다. 추가 AI 해석은 사용할 수 없습니다.");
          return;
        }
        if (!active()) return;
        log("LLM", "상위 5건의 추가 해석을 요청합니다.", "해석 중");
        const explanations: unknown = await explain(open.slice(0, 5), selectedOS);
        if (!active()) return;
        if (!Array.isArray(explanations) || !explanations.every(record)) throw new Error("추가 해석의 응답 형식이 올바르지 않습니다.");
        const byFingerprint = new Map<string, JsonRecord>();
        for (const explanation of explanations) for (const fingerprint of [explanation.fingerprint, ...(Array.isArray(explanation.covers) ? explanation.covers : [])])
          if (typeof fingerprint === "string") byFingerprint.set(fingerprint, explanation);
        mapped = mapped.map(finding => byFingerprint.has(finding.id) ? mergeExplanation(finding, byFingerprint.get(finding.id)) : finding);
        reportInput = { ...reportInput, explain_results: explanations };
        log("LLM", `추가 해석 ${explanations.filter(item => item.status === "done").length}건 수신. 코드 해결 여부는 엔진 상태로 표시합니다.`, "해석 수신");
        publish("엔진 결과와 추가 AI 해석을 표시합니다.");
      } catch (error) {
        log("LLM", `${error instanceof Error ? error.message : "추가 해석 실패"} · 엔진 결과를 유지합니다.`, "해석 실패", "warn");
        publish("추가 AI 해석에 실패했습니다. 엔진 검사 결과는 유지됩니다.");
      }
    } catch (error) {
      if (!active()) return;
      const message = error instanceof Error ? error.message : "검사 요청을 완료하지 못했습니다.";
      log("error", message, "실패", "warn");
      change(value => ({ ...value, error: message, message: value.result ? "이전 검사 결과를 유지합니다. 아래 결과의 저장소를 확인하세요." : "" }));
    } finally {
      busy.current = false;
      if (active()) change(value => ({ ...value, isScanning: false }));
    }
  }
  return <RepositoryContext.Provider value={{ ...state,
    setRepoInput: repoInput => change(current => ({ ...current, repoInput, error: "" })),
    setOS: os => change(current => ({ ...current, os })), setHosting: hosting => change(current => ({ ...current, hosting })),
    selectFinding: selectedFindingId => change(current => ({ ...current, selectedFindingId })),
    showMessage: message => change(current => ({ ...current, message })), runScan,
    togglePending: id => change(current => {
      if (current.isScanning || !current.findings.some(f => f.id === id && !f.fixed)) return current;
      const pendingIds = current.pendingIds.includes(id) ? current.pendingIds.filter(value => value !== id) : [...current.pendingIds, id];
      return { ...current, pendingIds, message: pendingIds.includes(id) ? "조치 표시를 저장했습니다. 실제 재검사로 해결 여부를 확인하세요." : "조치 표시를 취소했습니다." };
    }, true),
  }}>{children}</RepositoryContext.Provider>;
}

export function useRepository() {
  const value = useContext(RepositoryContext);
  if (!value) throw new Error("RepositoryProvider is missing");
  return value;
}
