// Red–Blue 실검증 API (/api/verify): 접수 → 작업 번호 → 2초마다 조회. 모양은 backend/app/verify/schemas.py 의 VerifyResult 입니다.
// 테스트가 이 파일만 변환해 불러오므로 다른 모듈을 import 하지 않습니다.

export type VerifyStatus = "verified" | "not_reproduced" | "fix_failed" | "error";
export type AttackVerdict = "verified" | "not_reproduced" | "fix_failed";

export interface HttpRequestSpec { method?: string; path: string; query?: Record<string, string>; body?: string | null }
export interface AttackDefinition { id: string; cwe?: string; rule_id?: string; runtime?: boolean; request?: HttpRequestSpec; success_when?: string; note?: string }
export interface AttackOutcome {
  id: string; before_succeeded: boolean; after_succeeded: boolean;
  before_status: number | null; after_status: number | null;
  before_evidence: string | null; after_evidence: string | null; verdict: AttackVerdict;
}
export interface TestOutcome { ok: boolean | null; passed: number | null; failed: number | null }
export interface Isolation { network_isolated: boolean | null; non_root: boolean | null; caps_dropped: boolean | null; no_new_privs: boolean | null }
export interface VerifyResult {
  status: VerifyStatus; message: string; sandbox: "docker" | "local";
  isolation: Isolation; isolation_confirmed: boolean; attacks: AttackOutcome[];
  before_tests: TestOutcome; after_tests: TestOutcome; duration_sec: number;
}
export interface VerifyJob {
  job_id: string; status: "queued" | "running" | "done" | "failed";
  reused: boolean; finished_at?: string;
  result: VerifyResult | null; error: { code?: string; message?: string } | null;
  target?: string; mode: VerifyMode; attacks: AttackDefinition[]; patched_files: string[]; patch_diff: string;
  ai: AiPlan | null;
}
/** reference: 사람이 쓴 기준 수정본, ai: GPU Red·Blue가 만든 공격·수정본 (Docker 격리에서만 실행) */
export type VerifyMode = "reference" | "ai";
export interface AiSkipped { fingerprint: string; stage: string; reason: string }
export interface AiPlan { red_reasons: Record<string, string>; patch_summaries: Record<string, string>; skipped: AiSkipped[] }

const stringMap = (v: unknown): Record<string, string> => record(v)
  ? Object.fromEntries(Object.entries(v).filter((e): e is [string, string] => typeof e[1] === "string")) : {};

function parseAi(v: unknown): AiPlan | null {
  if (!record(v)) return null;
  const skipped = Array.isArray(v.skipped) ? v.skipped.filter((s): s is AiSkipped => record(s)
    && typeof s.fingerprint === "string" && typeof s.stage === "string" && typeof s.reason === "string") : [];
  return { red_reasons: stringMap(v.red_reasons), patch_summaries: stringMap(v.patch_summaries), skipped };
}

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const nullable = (v: unknown, type: string) => v === null || v === undefined || typeof v === type;
const triState = (v: unknown) => v === null || v === undefined || typeof v === "boolean";

function validResult(v: unknown): v is VerifyResult {
  if (!record(v) || !["verified", "not_reproduced", "fix_failed", "error"].includes(String(v.status))) return false;
  if (typeof v.message !== "string" || !Array.isArray(v.attacks) || !record(v.isolation)) return false;
  const iso = v.isolation;
  if (!["network_isolated", "non_root", "caps_dropped", "no_new_privs"].every(k => triState(iso[k]))) return false;
  const tests = [v.before_tests, v.after_tests];
  if (!tests.every(t => record(t) && triState(t.ok) && nullable(t.passed, "number") && nullable(t.failed, "number"))) return false;
  return v.attacks.every(a => record(a) && typeof a.id === "string" && typeof a.before_succeeded === "boolean"
    && typeof a.after_succeeded === "boolean" && ["verified", "not_reproduced", "fix_failed"].includes(String(a.verdict))
    && nullable(a.before_evidence, "string") && nullable(a.after_evidence, "string"));
}

/** 서버 응답을 확인해 화면이 쓰는 모양으로 돌려줍니다. 모양이 다르면 null (화면이 깨지는 대신 오류로 보여 줌). */
export function parseVerifyJob(v: unknown): VerifyJob | null {
  if (!record(v) || typeof v.job_id !== "string" || !["queued", "running", "done", "failed"].includes(String(v.status))) return null;
  if (typeof v.reused !== "boolean") return null;
  if (v.finished_at !== undefined && (typeof v.finished_at !== "string" || !Number.isFinite(Date.parse(v.finished_at)))) return null;
  if (v.status === "done" && !validResult(v.result)) return null;
  const attacks = Array.isArray(v.attacks) ? v.attacks.filter((a): a is AttackDefinition => record(a) && typeof a.id === "string") : [];
  return {
    job_id: v.job_id, status: v.status as VerifyJob["status"],
    reused: v.reused, finished_at: v.finished_at as string | undefined,
    result: v.status === "done" ? v.result as VerifyResult : null,
    error: record(v.error) ? { code: typeof v.error.code === "string" ? v.error.code : undefined, message: typeof v.error.message === "string" ? v.error.message : undefined } : null,
    target: typeof v.target === "string" ? v.target : undefined,
    mode: v.mode === "ai" ? "ai" : "reference",
    attacks,
    patched_files: Array.isArray(v.patched_files) ? v.patched_files.filter((f): f is string => typeof f === "string") : [],
    patch_diff: typeof v.patch_diff === "string" ? v.patch_diff : "",
    ai: parseAi(v.ai),
  };
}

/** 사람이 읽는 공격 요청 한 줄. 예) GET /api/orders?orderId=0 OR 1=1 (주소 인코딩 없이 보여 줌) */
export function requestLine(req?: HttpRequestSpec): string {
  if (!req) return "";
  const query = Object.entries(req.query ?? {}).map(([k, v]) => `${k}=${v}`).join("&");
  return `${req.method ?? "GET"} ${req.path}${query ? `?${query}` : ""}`;
}

export function testsLabel(t: TestOutcome): string {
  if (t.ok === null || t.ok === undefined) return "실행 결과 없음";
  const total = t.passed !== null && t.failed !== null ? t.passed + t.failed : null;
  if (t.ok) return total ? `${t.passed}/${total} 통과` : "통과";
  return total ? `${t.failed}건 실패 (${t.passed}/${total} 통과)` : "실패";
}

/**
 * 판정 메시지를 사람이 읽을 수 있게 풀어 씁니다. 특히 "수정 후 앱이 뜨지 않았습니다"는 실검증이 잘못된 수정을
 * 걸러낸 결과인데, 그대로 두면 검사 실패처럼 읽힙니다.
 */
export function verdictHelp(job: Pick<VerifyJob, "mode" | "result">): string[] {
  const result = job.result;
  if (!result) return [];
  if (result.status === "fix_failed" && /수정 후 앱이/.test(result.message)) return [
    "수정본을 적용한 앱이 시작되지 않거나 요청에 응답하지 않았습니다. 수정이 앱 기능을 망가뜨렸다는 뜻이라, 이 수정본은 그대로 쓰면 안 됩니다.",
    job.mode === "ai"
      ? "AI(Blue)가 만든 수정본에서 자주 생기는 문제입니다(예: 응답을 보내는 줄까지 지움). 실검증이 이런 잘못된 수정을 배포 전에 걸러낸 결과입니다. 아래 '수정 내용 보기'에서 무엇이 바뀌었는지 확인하고, 다시 실행하거나 기준 수정본과 비교해 보세요."
      : "아래 '수정 내용 보기'에서 무엇이 바뀌었는지 확인하세요.",
  ];
  if (result.status === "fix_failed") return ["수정 후에도 공격이 통하거나, 수정 전에는 통과하던 기능 테스트가 깨졌습니다. 공격별 결과와 기능 테스트를 확인하세요."];
  if (result.status === "not_reproduced") return ["수정 전에도 공격이 통하지 않았습니다. 이 탐지는 실제로는 위험하지 않은 오탐일 수 있습니다."];
  return [];
}

export const verdictLabels: Record<VerifyStatus, { label: string; tone: "ok" | "danger" | "warn" | "muted" }> = {
  verified: { label: "검증됨", tone: "ok" },
  fix_failed: { label: "수정 미흡", tone: "danger" },
  not_reproduced: { label: "재현 안 됨 · 오탐 후보", tone: "warn" },
  error: { label: "실행 실패", tone: "muted" },
};

export const attackVerdictLabels: Record<AttackVerdict, string> = {
  verified: "수정 전 성공 → 수정 후 차단",
  fix_failed: "수정 후에도 공격 성공",
  not_reproduced: "수정 전에도 공격 실패",
};

export const isolationLabels: [keyof Isolation, string][] = [
  ["network_isolated", "인터넷 차단"],
  ["non_root", "일반 사용자로 실행"],
  ["caps_dropped", "특수 권한 제거"],
  ["no_new_privs", "권한 상승 금지"],
];

function apiError(data: unknown, fallback: string): Error {
  const detail = record(data) ? data.detail : undefined;
  if (record(detail) && typeof detail.message === "string") return new Error(detail.message);
  if (typeof detail === "string") return new Error(detail);
  return new Error(fallback);
}

/** 실검증을 접수하고 끝날 때까지 조회합니다. onStatus로 queued·running 을 알려 줍니다. */
export async function runVerify(options: { mode?: VerifyMode; onStatus?: (status: VerifyJob["status"]) => void; intervalMs?: number; timeoutMs?: number; isCancelled?: () => boolean } = {}): Promise<VerifyJob> {
  const { mode = "reference", onStatus, intervalMs = 2000, timeoutMs = 10 * 60 * 1000, isCancelled } = options;
  const res = await fetch("/api/verify", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ target: "demo", mode }) });
  const data: unknown = await res.json().catch(() => ({}));
  if (!res.ok) throw apiError(data, `실검증 접수 실패 (${res.status})`);
  const jobId = record(data) && typeof data.job_id === "string" ? data.job_id : null;
  if (!jobId) throw new Error("실검증 접수 응답이 올바르지 않습니다.");
  let waitBeforePoll = !record(data) || data.status !== "done";
  if (waitBeforePoll) onStatus?.("queued");
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (waitBeforePoll) await new Promise(resolve => setTimeout(resolve, intervalMs));
    waitBeforePoll = true;
    if (isCancelled?.()) throw new Error("실검증 조회를 멈췄습니다.");
    const response = await fetch(`/api/verify/${encodeURIComponent(jobId)}`, { cache: "no-store" });
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) throw apiError(body, `실검증 상태 조회 실패 (${response.status})`);
    const job = parseVerifyJob(body);
    if (!job) throw new Error("실검증 응답 형식이 올바르지 않습니다.");
    if (job.status === "failed") throw new Error(job.error?.message || "실검증에 실패했습니다.");
    if (job.status === "done") return job;
    onStatus?.(job.status);
  }
  throw new Error("실검증이 10분 안에 끝나지 않았습니다.");
}
