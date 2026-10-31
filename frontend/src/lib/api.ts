// 백엔드 연결: /api/* 는 next.config.ts rewrites 로 FastAPI(:8000)에 전달됩니다.
import type { Finding } from "@/types/security";
import type { AssessResponse, Deadline, FilingKind, FilingNeed, FilingReport, FilingRequest, IncidentInput, ReportBadge, ReportCard, ReportField, ReportSection } from "@/types/incident";

/* eslint-disable @typescript-eslint/no-explicit-any */
type EngineItem = any;
type ExplainResult = any;

const now = () => new Date().toTimeString().slice(0, 8);
export { now };

// 검사 접수 → 3초마다 진행 상태 조회 (검사는 1~3분 걸려서 응답을 기다리지 않고 작업 번호로 확인)
export async function startScan(repoUrl: string, previous?: unknown, onStatus?: (s: string) => void) {
  const res = await fetch("/api/scans", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl, previous: previous ?? null }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail?.message || data?.detail || `검사 접수 실패 (${res.status})`);
  const started = Date.now();
  while (Date.now() - started < 15 * 60 * 1000) {
    await new Promise((r) => setTimeout(r, 3000));
    const st = await fetch(`/api/scans/${data.job_id}`);
    const job = await st.json().catch(() => ({}));
    if (!st.ok) throw new Error(job?.detail?.message || `검사 상태 조회 실패 (${st.status})`);
    onStatus?.(job.status);
    if (job.status === "done") return job.result;
    if (job.status === "failed") throw new Error(job.error?.message || "검사 실패");
  }
  throw new Error("검사가 15분 안에 끝나지 않았습니다.");
}

export async function llmHealthy(): Promise<boolean> {
  try {
    const res = await fetch("/api/llm/health", { cache: "no-store", signal: AbortSignal.timeout(12_000) });
    return res.ok;
  } catch {
    return false;
  }
}

// 백엔드 임시 해석 대기열(PreviewJobs)이 동시에 실행하는 작업 수와 같게 둡니다 (#59).
// 한 건씩 기다리면 GPU 슬롯 하나가 계속 놀고, 이보다 많이 보내면 대기열만 차서 다른 사용자가 밀립니다.
export const LLM_PARALLEL = 2;

export type Settled<R> = { ok: true; value: R } | { ok: false; error: unknown };

/**
 * items를 최대 limit건씩 동시에 처리하고, 한 건이 끝날 때마다 onSettled로 바로 알려 줍니다.
 * 실패한 건이 있어도 나머지는 계속 처리합니다. 무제한 Promise.all이 아니라 limit개의 작업자가 차례로 가져갑니다.
 */
export async function runLimited<T, R>(
  items: T[],
  run: (item: T, index: number) => Promise<R>,
  onSettled: (index: number, outcome: Settled<R>) => void,
  limit = LLM_PARALLEL,
): Promise<void> {
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next++;
      let outcome: Settled<R>;
      try {
        outcome = { ok: true, value: await run(items[index], index) };
      } catch (error) {
        outcome = { ok: false, error };
      }
      onSettled(index, outcome);
    }
  };
  const workers = Math.max(1, Math.min(Math.floor(limit) || 1, items.length));
  await Promise.all(Array.from({ length: workers }, worker));
}

export async function explain(findings: unknown[]) {
  const res = await fetch("/api/llm/explain/tasks", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ findings, mode: "red_blue" }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail?.message || `LLM 해석 실패 (${res.status})`);
  if (typeof data.job_id !== "string") throw new Error("LLM 작업 응답이 올바르지 않습니다.");
  const started = Date.now();
  while (Date.now() - started < 16 * 60 * 1000) {
    const response = await fetch(`/api/llm/explain/tasks/${encodeURIComponent(data.job_id)}`,
      { cache: "no-store", signal: AbortSignal.timeout(15_000) });
    const job = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(job?.detail?.message || `LLM 상태 조회 실패 (${response.status})`);
    if (job.status === "failed") throw new Error(job.error?.message || "LLM 해석에 실패했습니다.");
    if (job.status === "done") {
      if (!Array.isArray(job.result?.results)) throw new Error("LLM 결과 형식이 올바르지 않습니다.");
      return job.result.results as ExplainResult[];
    }
    if (!["queued", "running"].includes(job.status)) throw new Error("LLM 작업 상태가 올바르지 않습니다.");
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  throw new Error("LLM 해석이 제한 시간 안에 끝나지 않았습니다.");
}

// 비전공자용 점검 리포트 (실제 검사 결과로). format=html 이면 인쇄용 HTML, markdown 이면 붙여 넣기용
export async function plainReport(body: unknown, format: "html" | "markdown" = "html") {
  const res = await fetch(`/api/reports/plain?format=${format}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`리포트 생성 실패 (${res.status}): ${text.slice(0, 200)}`);
  return text;
}

const filingPaths: Record<FilingKind, string> = { incident_24h: "incident-24h", privacy_72h: "privacy-72h" };
const reportRecord = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const reportStrings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === "string");
const nullableText = (value: unknown) => value === null || value === undefined || typeof value === "string";
const reportDate = (value: unknown): value is string => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value));

function validDeadline(value: unknown): value is Deadline {
  return reportRecord(value) && typeof value.label === "string" && typeof value.basis === "string"
    && reportDate(value.starts_at) && reportDate(value.due_at) && typeof value.hours === "number" && Number.isFinite(value.hours) && value.hours > 0
    && Number.isInteger(value.remaining_minutes) && typeof value.overdue === "boolean"
    && (value.stopped_at == null || reportDate(value.stopped_at));
}
function validBadge(value: unknown): value is ReportBadge {
  return reportRecord(value) && typeof value.text === "string" && ["danger", "warning", "ok", "info", "muted"].includes(String(value.tone));
}
function validField(value: unknown): value is ReportField {
  return reportRecord(value) && typeof value.label === "string" && (value.value === null || typeof value.value === "string")
    && typeof value.required === "boolean" && typeof value.auto === "boolean" && nullableText(value.hint);
}
function validCard(value: unknown): value is ReportCard {
  return reportRecord(value) && typeof value.title === "string" && Array.isArray(value.badges) && value.badges.every(validBadge)
    && reportStrings(value.paragraphs) && Array.isArray(value.fields) && value.fields.every(validField) && reportStrings(value.steps);
}
function validSection(value: unknown): value is ReportSection {
  return reportRecord(value) && typeof value.heading === "string" && reportStrings(value.paragraphs) && reportStrings(value.bullets) && reportStrings(value.steps)
    && Array.isArray(value.fields) && value.fields.every(validField) && Array.isArray(value.cards) && value.cards.every(validCard);
}
function validNeed(value: unknown): value is FilingNeed {
  return reportRecord(value) && (value.kind === "incident_24h" || value.kind === "privacy_72h")
    && typeof value.required === "boolean" && reportStrings(value.reasons) && (value.deadline == null || validDeadline(value.deadline))
    && (!value.required || validDeadline(value.deadline));
}
function reportFailure(body: string, status: number, label: string): Error {
  let detail = "다시 시도하고 입력 내용을 확인해 주세요.";
  try {
    const data: unknown = JSON.parse(body);
    if (reportRecord(data)) {
      if (typeof data.detail === "string") detail = data.detail;
      else if (reportRecord(data.detail) && typeof data.detail.message === "string") detail = data.detail.message;
      else if (Array.isArray(data.detail)) {
        const labels: Record<string, string> = { discovered_at: "인지 시각", occurred_at: "발생 시각", personal_info: "개인정보 확인", findings: "관련 검사 발견", incident: "사고 정보" };
        const errors = data.detail.filter(reportRecord).slice(0, 3).map(error => {
          const fields = Array.isArray(error.loc) ? error.loc.filter(part => typeof part === "string") : [];
          const field = fields.find(part => typeof part === "string" && part in labels);
          return `${field ? labels[String(field)] : "입력 항목"}: ${typeof error.msg === "string" ? error.msg : "값을 확인해 주세요."}`;
        });
        if (errors.length) detail = errors.join(" · ");
      }
    }
  } catch { /* Never surface an HTML proxy error as a report or echo a submitted value. */ }
  return new Error(`${label} 실패 (${status}): ${detail.slice(0, 240)}`);
}

async function requestIncidentReport(path: string, body: unknown, label: string) {
  let response: Response;
  let content: string;
  try {
    response = await fetch(`/api/reports/${path}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      cache: "no-store", signal: AbortSignal.timeout(20_000),
    });
    content = await response.text();
  } catch (error) {
    if (error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name))
      throw new Error(`${label} 응답 시간이 지났습니다. 입력은 유지되니 다시 시도해 주세요.`);
    throw new Error(`${label} 서버에 연결하지 못했습니다. 네트워크를 확인하고 다시 시도해 주세요.`);
  }
  if (!response.ok) throw reportFailure(content, response.status, label);
  return { content, contentType: response.headers.get("content-type") ?? "" };
}

export async function assessIncident(incident: IncidentInput): Promise<AssessResponse> {
  const { content } = await requestIncidentReport("assess", incident, "신고 대상 확인");
  let value: unknown;
  try { value = JSON.parse(content); } catch { throw new Error("신고 대상 확인 응답 형식이 올바르지 않습니다."); }
  if (!reportRecord(value) || !Array.isArray(value.needs) || value.needs.length !== 2 || !value.needs.every(validNeed)
    || new Set(value.needs.map(need => need.kind)).size !== 2)
    throw new Error("신고 대상 확인 응답 형식이 올바르지 않습니다.");
  return { needs: value.needs };
}

export async function getFilingReport(body: FilingRequest, kind: FilingKind): Promise<FilingReport> {
  if (!filingPaths[kind]) throw new Error("지원하는 신고서 종류를 선택해 주세요.");
  const { content } = await requestIncidentReport(`${filingPaths[kind]}?format=json`, body, "신고서 생성");
  let value: unknown;
  try { value = JSON.parse(content); } catch { throw new Error("신고서 응답 형식이 올바르지 않습니다."); }
  if (!reportRecord(value) || value.kind !== kind || typeof value.title !== "string" || !nullableText(value.subtitle)
    || !reportDate(value.generated_at) || !validBadge(value.status) || (value.deadline != null && !validDeadline(value.deadline))
    || !Array.isArray(value.sections) || !value.sections.every(validSection) || !reportStrings(value.missing)
    || !reportStrings(value.submit_to) || !nullableText(value.disclaimer))
    throw new Error("신고서 응답 형식이 올바르지 않습니다.");
  return value as FilingReport;
}

export async function getFilingDocument(body: FilingRequest, kind: FilingKind, format: "html" | "markdown"): Promise<string> {
  if (!filingPaths[kind] || !["html", "markdown"].includes(format)) throw new Error("지원하는 문서 형식을 선택해 주세요.");
  const { content, contentType } = await requestIncidentReport(`${filingPaths[kind]}?format=${format}`, body, "신고 문서 생성");
  const expectedType = format === "html" ? /^text\/html\b/i : /^text\/(?:markdown|plain)\b/i;
  const expectedContent = format === "html" ? /<(?:!doctype\s+html|html|body|article|main|section)\b/i : /^#{1,6}\s/m;
  if (!expectedType.test(contentType) || !content.trim() || !expectedContent.test(content))
    throw new Error("신고 문서 응답 형식이 올바르지 않습니다. 다시 생성해 주세요.");
  return content;
}

// 마지막 검사 결과를 브라우저에 보관 (새로고침해도 유지). 서버 DB 저장은 추후 개발 예정
const STORE_KEY = "72hours:last-scan:v1";
export function saveLast(data: unknown) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(data));
  } catch {
    /* 용량 초과·비공개 창이면 저장 없이 계속 */
  }
}
export function loadLast<T>(): T | null {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

const CHANGE_LABEL: Record<string, string> = {
  new: "새로 발견", persisting: "계속 남아 있음", resolved: "해결 확인", unverifiable: "확인 불가",
};

const SEV_DECISION: Record<string, Finding["decision"]> = {
  critical: "act", high: "act", medium: "attend", low: "trackstar", unknown: "trackstar",
};
const DECISION_LABEL: Record<Finding["decision"], string> = {
  act: "act · 지금 바로", attend: "attend · 이번 주", trackstar: "track · 지켜보기",
};

export function itemToFinding(it: EngineItem): Finding {
  const decision = SEV_DECISION[it.severity] ?? "attend";
  const tool = String(it.id || "").split(":")[0];
  const cmd = it.fix_hint?.command || "";
  return {
    id: it.id,
    decision,
    decisionLabel: DECISION_LABEL[decision],
    title: String(it.title ?? ""),
    file: `${it.where || it.package?.name || ""} · ${tool}${it.cwe?.length ? " · " + it.cwe[0] : ""}`,
    verdict: it.status === "code_resolved" ? "해결 확인"
      : it.status === "runtime_check_needed" ? "키 재발급 필요"
      : it.status === "out_of_scope" ? "확인 불가"
      : CHANGE_LABEL[it.change] || "엔진 탐지",
    verdictType: it.status === "code_resolved" ? "ok" : "warn",
    confidence: `위험도 ${it.severity}`,
    scope: it.kind,
    fixed: it.status === "code_resolved",
    desc: it.what || it.title,
    redScenario: it.status === "code_resolved" ? "재검사에서 해결된 항목으로 LLM 해석을 생략합니다."
      : "LLM 해석 미요청 — 자동 해석은 상위 5개 항목 묶음까지 수행합니다. 현재는 엔진 결과입니다.",
    why: [it.status_label, ...(it.flags || []).map((x: any) => (typeof x === "string" ? x : x?.note || x?.flag))]
      .filter(Boolean)
      .map(String),
    commands: { windows: cmd, macos: cmd, linux: cmd },
    aiPrompt: `[72hours 보안 수정 지시 | 규칙: ${it.rule_id}]\n대상 위치: ${it.where || "-"}\n${it.what || it.title}\n${it.fix_hint?.text || ""}`,
  };
}

export function mergeExplanation(f: Finding, r: ExplainResult): Finding {
  if (r?.status === "failed") return { ...f, verdict: "LLM 해석 실패", verdictType: "warn",
    redScenario: `LLM 해석에 실패했습니다 (${r.error_code || "LLM_ERROR"}). 엔진 결과와 기본 수정 안내는 유지됩니다.` };
  if (r?.status === "skipped") return { ...f, redScenario: `LLM 해석 생략: ${r.reason || "해석 대상이 아닙니다."}` };
  const e = r?.explanation;
  if (!e) return f;
  const decisions: Record<string, Finding["decision"]> = { act: "act", attend: "attend", "track*": "trackstar", track: "trackstar" };
  const decision = decisions[e.risk?.decision] || f.decision;
  const passed = e.red_verdict === "pass" && !e.needs_manual_review;
  const cmds: Record<string, string> = {};
  for (const a of e.guide?.actions || [])
    for (const b of a.commands || []) cmds[b.os] = [cmds[b.os], `# ${a.title}`, ...(b.lines || [])].filter(Boolean).join("\n");
  return {
    ...f,
    decision,
    decisionLabel: DECISION_LABEL[decision],
    title: e.summary || f.title,
    desc: e.why_risky || f.desc,
    redScenario: e.attack_scenario || f.redScenario,
    verdict: passed ? "Red 통과" : e.needs_manual_review || e.red_verdict ? "수동 확인" : "Blue 해석",
    verdictType: passed ? "ok" : "warn",
    why: e.risk?.factors?.length ? e.risk.factors.map((factor: any) => factor.reason)
      : (e.fix_steps || []).map((s: any) => `${s.title}: ${s.detail}`),
    aiPrompt: e.ai_fix_prompt || f.aiPrompt,
    commands: {
      windows: cmds.windows || f.commands.windows,
      macos: cmds.macos || f.commands.macos,
      linux: cmds.linux || f.commands.linux,
    },
  };
}
