import type { FilingFinding, FilingKind, FilingReport, FilingRequest, IncidentForm, IncidentInput, IncidentType, PersonalInfoBreach } from "@/types/incident";

export const initialIncidentForm: IncidentForm = {
  organizationName: "", serviceName: "", discoveredAt: "", occurredAt: "", summary: "", cause: "", damage: "", actions: "",
  department: "", contactName: "", contactPhone: "", contactEmail: "", incidentTypes: [], incidentStatus: "unknown", filingType: "unknown", leakState: "unknown",
  affectedCount: "", countIsEstimate: false, personalItems: "", includesSensitive: "unknown", includesUniqueId: "unknown",
  externalAccess: "unknown", recoveredLowRisk: "unknown", subjectsNotified: "unknown", notifyMethod: "", notifiedAt: "",
};

export const incidentTypeLabels: Record<IncidentType, string> = {
  hacking: "해킹·무단 침입", malware: "악성코드·랜섬웨어", ddos: "서비스 거부 공격", defacement: "홈페이지 위·변조",
  account_takeover: "계정 탈취", data_leak: "데이터 유출", other: "기타·조사 중",
};

function text(value: string, label: string, max: number): string | null {
  const cleaned = value.trim();
  if ([...cleaned].length > max) throw new Error(`${label}은 ${max}자 이내로 입력해 주세요.`);
  return cleaned || null;
}

// datetime-local fields are labelled Korea time in the UI. Never interpret them in the device's timezone.
function koreanTime(value: string, label: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!match) throw new Error(`${label}을 올바른 한국 시각으로 입력해 주세요.`);
  const [, year, month, day, hour, minute, second = "00"] = match;
  const expected = [year, month, day, hour, minute, second].map(Number);
  const check = new Date(0);
  check.setUTCFullYear(expected[0], expected[1] - 1, expected[2]);
  check.setUTCHours(expected[3], expected[4], expected[5], 0);
  const actual = [check.getUTCFullYear(), check.getUTCMonth() + 1, check.getUTCDate(), check.getUTCHours(), check.getUTCMinutes(), check.getUTCSeconds()];
  if (expected[0] < 1 || expected.some((part, index) => part !== actual[index]))
    throw new Error(`${label}에 존재하는 날짜와 시각을 입력해 주세요.`);
  return `${year}-${month}-${day}T${hour}:${minute}:${second}+09:00`;
}

function personalInfo(form: IncidentForm): PersonalInfoBreach | null {
  if (form.leakState === "unknown") return null;
  if (form.leakState === "none") return { leaked: "none" };
  if (!["suspected", "confirmed"].includes(form.leakState)) throw new Error("개인정보 유출 확인 상태를 다시 선택해 주세요.");
  const count = form.affectedCount.trim();
  if (count && (!/^\d+$/.test(count) || !Number.isSafeInteger(Number(count))))
    throw new Error("유출 규모는 0 이상의 정수로 입력하거나 모르면 비워 두세요.");
  const items = form.personalItems.split(/[,\n]/).map(item => item.trim()).filter(Boolean);
  if (items.length > 30) throw new Error("개인정보 항목은 30개까지 입력할 수 있습니다.");
  const result: PersonalInfoBreach = {
    leaked: form.leakState, affected_count: count ? Number(count) : null, count_is_estimate: form.countIsEstimate, items,
  };
  const answers = [
    ["includes_sensitive", form.includesSensitive], ["includes_unique_id", form.includesUniqueId],
    ["external_unauthorized_access", form.externalAccess], ["recovered_low_risk", form.recoveredLowRisk],
    ["subjects_notified", form.subjectsNotified],
  ] as const;
  for (const [key, answer] of answers) {
    if (answer === "yes" || answer === "no") result[key] = answer === "yes";
    else if (answer !== "unknown") throw new Error("추가 확인 항목을 다시 선택해 주세요.");
  }
  if (form.subjectsNotified === "yes") {
    result.notified_at = form.notifiedAt ? koreanTime(form.notifiedAt, "정보주체에게 통지한 시각") : null;
    result.notify_method = text(form.notifyMethod, "통지 방법", 200);
  }
  return result;
}

export function buildIncidentInput(form: IncidentForm): IncidentInput {
  if (!form.discoveredAt) throw new Error("문제를 인지한 시각을 입력해 주세요.");
  if (!["unknown", "ongoing", "contained", "recovered"].includes(form.incidentStatus))
    throw new Error("사고 대응 상태를 올바르게 선택해 주세요.");
  if (!["unknown", "initial", "supplement"].includes(form.filingType))
    throw new Error("최초 신고 또는 보완 신고 여부를 올바르게 선택해 주세요.");
  if (form.incidentTypes.length > 7 || form.incidentTypes.some(kind => !(kind in incidentTypeLabels)))
    throw new Error("사고 유형을 올바르게 선택해 주세요.");
  const actions = form.actions.split(/\r?\n/).map(action => action.trim()).filter(Boolean);
  if (actions.length > 30) throw new Error("조치 기록은 줄마다 한 건씩 30건까지 입력할 수 있습니다.");
  return {
    organization: {
      name: text(form.organizationName, "기관명", 200), service_name: text(form.serviceName, "서비스명", 200),
      department: text(form.department, "담당 부서", 100), contact_name: text(form.contactName, "담당자", 50),
      contact_phone: text(form.contactPhone, "연락처", 30), contact_email: text(form.contactEmail, "이메일", 200),
    },
    discovered_at: koreanTime(form.discoveredAt, "문제를 인지한 시각"),
    occurred_at: form.occurredAt ? koreanTime(form.occurredAt, "사고 발생 시각") : null,
    incident_types: [...new Set(form.incidentTypes)],
    ...(form.incidentStatus === "unknown" ? {} : { status: form.incidentStatus }),
    ...(form.filingType === "unknown" ? {} : { is_supplement: form.filingType === "supplement" }),
    summary: text(form.summary, "확인한 사실", 1000), cause: text(form.cause, "원인", 2000), damage: text(form.damage, "피해 내용", 2000),
    actions_taken: actions.map(action => ({ action: text(action, "조치 내용", 500)! })),
    related_fingerprints: [], personal_info: personalInfo(form),
  };
}

// These describe unanswered questions, not legal thresholds. The API remains the source of assessment rules.
export function getAssessmentGaps(form: IncidentForm, kind: FilingKind): string[] {
  if (kind === "incident_24h") {
    const gaps = [];
    if (!form.incidentTypes.length) gaps.push("사고 유형을 아직 확인하지 않았습니다.");
    // The API reads external access only from personal_info, so ask it only where the form can send it.
    const sendsPersonalInfo = form.leakState === "suspected" || form.leakState === "confirmed";
    if (sendsPersonalInfo && form.externalAccess === "unknown") gaps.push("외부의 불법 접근 여부를 아직 확인하지 않았습니다.");
    return gaps;
  }
  if (form.leakState === "unknown") return ["개인정보 유출 여부를 아직 확인하지 않았습니다."];
  if (form.leakState === "none") return [];
  const gaps = [];
  if (!form.affectedCount.trim()) gaps.push("유출 규모를 아직 확인하지 않았습니다.");
  if (form.includesSensitive === "unknown") gaps.push("민감정보 포함 여부를 아직 확인하지 않았습니다.");
  if (form.includesUniqueId === "unknown") gaps.push("고유식별정보 포함 여부를 아직 확인하지 않았습니다.");
  if (form.externalAccess === "unknown") gaps.push("외부의 불법 접근 여부를 아직 확인하지 않았습니다.");
  if (form.recoveredLowRisk === "unknown") gaps.push("유출 정보 회수·삭제 및 피해 가능성을 아직 확인하지 않았습니다.");
  return gaps;
}

function isFinding(value: unknown): value is FilingFinding {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  const lengths = { fingerprint: 200, tool: 50, rule_id: 200, title: 500 };
  for (const [key, limit] of Object.entries(lengths)) {
    if (typeof item[key] !== "string" || [...item[key]].length > limit) return false;
  }
  return !!(item.fingerprint as string).trim() && ["dependency", "code", "secret", "config"].includes(String(item.category))
    && ["critical", "high", "medium", "low", "info", "unknown"].includes(String(item.severity));
}

export function buildFilingRequest(form: IncidentForm, selectedFindings: unknown[]): FilingRequest {
  if (selectedFindings.length > 50) throw new Error("관련 검사 발견은 50개까지 선택할 수 있습니다.");
  if (!selectedFindings.every(isFinding)) throw new Error("선택한 검사 발견의 형식이 올바르지 않습니다. 검사 결과를 다시 확인해 주세요.");
  const fingerprints = selectedFindings.map(finding => finding.fingerprint);
  if (new Set(fingerprints).size !== fingerprints.length) throw new Error("관련 검사 발견에 중복된 항목이 있습니다.");
  return { incident: { ...buildIncidentInput(form), related_fingerprints: fingerprints }, findings: [...selectedFindings] };
}

// ── Server-driven flow ──
// The reports API already decides which fields are missing and which values it suggested (auto). The UI asks only
// the facts the API would otherwise default, then maps the API's missing labels back onto the shared incident form.

/** datetime-local value for the current Korea time. KST has no daylight saving, so a fixed +9h offset is exact. */
export function koreaNow(date = new Date()): string {
  return new Date(date.getTime() + 9 * 3_600_000).toISOString().slice(0, 16);
}

/** Facts the API would silently default (status → ongoing, is_supplement → false, subjects_notified → false). */
export function draftBlockers(form: IncidentForm): Record<FilingKind, string[]> {
  const common: string[] = [];
  if (form.incidentStatus === "unknown") common.push("현재 대응 상태");
  if (form.filingType === "unknown") common.push("최초·보완 신고 구분");
  const privacy = [...common];
  if (form.leakState !== "suspected" && form.leakState !== "confirmed") privacy.push("개인정보 유출 의심 또는 확인");
  else if (form.subjectsNotified === "unknown") privacy.push("영향받은 분들께 이미 통지했는지");
  return { incident_24h: common, privacy_72h: privacy };
}

export type QuestionKey = "organizationName" | "occurredAt" | "cause" | "damage" | "actions" | "department" | "contactName"
  | "contactPhone" | "personalItems" | "affectedCount" | "summary";
export type QuestionField = { key: QuestionKey; label: string; type: "text" | "textarea" | "datetime-local" | "tel" | "number"; hint?: string };
export type RemainingQuestion = QuestionField & { kinds: FilingKind[] };

const actionsQuestion: QuestionField = { key: "actions", label: "지금까지 한 조치", type: "textarea", hint: "실제로 한 조치를 한 줄에 하나씩 적어 주세요." };
// Keys are FormField labels from backend/app/reports/filing.py. The API reports them as "<section> · <label>".
const questionFields: Record<string, QuestionField> = {
  "회사(기관) 이름": { key: "organizationName", label: "회사·기관명", type: "text" },
  "발생 일시": { key: "occurredAt", label: "사고가 실제로 일어난 시각 · 한국 시간", type: "datetime-local", hint: "모르면 비워 두고 먼저 신고한 뒤 확인되면 보완하세요." },
  "원인": { key: "cause", label: "확인한 원인", type: "textarea", hint: "모르면 ‘조사 중’이라고 적고, 확인되면 보완 신고하세요." },
  "피해 내용": { key: "damage", label: "확인한 피해 내용", type: "textarea", hint: "어떤 시스템·데이터가 어떻게 영향을 받았는지 확인한 만큼 적어 주세요." },
  "조치 사항": actionsQuestion,
  "피해 최소화 대책·조치 및 결과": actionsQuestion,
  "담당 부서": { key: "department", label: "담당 부서", type: "text" },
  "담당자": { key: "contactName", label: "담당자", type: "text" },
  "연락처(전화)": { key: "contactPhone", label: "연락처(전화)", type: "tel", hint: "신고 기관이 바로 연락할 수 있는 번호" },
  "유출된 개인정보 항목": { key: "personalItems", label: "유출된 개인정보 항목", type: "text", hint: "이메일, 이름처럼 항목명만 쉼표로 구분하세요." },
  "유출 규모": { key: "affectedCount", label: "영향받은 인원", type: "number", hint: "모르면 비워 두세요. 빈칸은 0명이 아닙니다." },
  "유출 시점과 경위": { key: "summary", label: "확인한 사실과 경위", type: "textarea" },
};

/** Turns each draft's `missing` list into one shared question per form field, so one answer fills both drafts. */
export function remainingQuestions(missing: Partial<Record<FilingKind, string[]>>): { questions: RemainingQuestion[]; unmapped: string[] } {
  const byKey = new Map<QuestionKey, RemainingQuestion>();
  const unmapped: string[] = [];
  for (const kind of ["incident_24h", "privacy_72h"] as const) {
    for (const entry of missing[kind] ?? []) {
      const split = entry.indexOf(" · ");
      const label = split >= 0 ? entry.slice(split + 3) : entry;
      const field = questionFields[label];
      if (!field) { if (!unmapped.includes(label)) unmapped.push(label); continue; }
      const existing = byKey.get(field.key);
      if (!existing) byKey.set(field.key, { ...field, kinds: [kind] });
      else if (!existing.kinds.includes(kind)) existing.kinds.push(kind);
    }
  }
  return { questions: [...byKey.values()], unmapped };
}

export type AutoSuggestion = { label: string; value: string; kinds: FilingKind[]; usableAs?: "cause" };
/** Values the API filled in by itself (`auto`), so the user can confirm them instead of retyping. */
export function autoSuggestions(reports: Partial<Record<FilingKind, FilingReport>>): AutoSuggestion[] {
  const found = new Map<string, AutoSuggestion>();
  for (const kind of ["incident_24h", "privacy_72h"] as const) {
    const fields = (reports[kind]?.sections ?? []).flatMap(section => [...section.fields, ...section.cards.flatMap(card => card.fields)]);
    for (const field of fields) {
      if (!field.auto || !field.value) continue;
      const id = `${field.label}\n${field.value}`;
      const existing = found.get(id);
      if (existing) { if (!existing.kinds.includes(kind)) existing.kinds.push(kind); continue; }
      found.set(id, { label: field.label, value: field.value, kinds: [kind], ...(field.label === "원인" ? { usableAs: "cause" as const } : {}) });
    }
  }
  return [...found.values()];
}

export type ScanFinding = { id: string; title: string; fixed: boolean };
const tokenLike = /[A-Za-z0-9_\-+/=]{24,}/g;
/** Actions the app already recorded during scanning: fixes verified by a rescan, and fixes the user marked by hand. */
export function scanActions(findings: ScanFinding[], pendingIds: string[]): string[] {
  const title = (value: string) => [...value.replace(tokenLike, "[가림]").trim()].slice(0, 200).join("");
  const actions: string[] = [];
  for (const finding of findings) {
    const line = finding.fixed ? `취약점 수정 후 재검사에서 해결 확인: ${title(finding.title)}`
      : pendingIds.includes(finding.id) ? `취약점 수정 조치(재검사 확인 전): ${title(finding.title)}` : "";
    if (line && !actions.includes(line)) actions.push(line);
  }
  return actions.slice(0, 30);
}

/** 검사를 실행했다는 사실 자체도 조치 기록입니다(점검 실시). 수정·재검사 전이라도 가져올 수 있게 한 줄로 만듭니다. */
export function scanCheckLine(repo: string, findings: { decision?: string }[]): string {
  const name = repo.replace(/^https:\/\/github\.com\//, "").slice(0, 200);
  const urgent = findings.filter(finding => finding.decision === "act").length;
  return `저장소 보안 점검 실시: ${name} · 발견 ${findings.length}건${urgent ? `(지금 바로 고칠 것 ${urgent}건)` : ""}`;
}

/** 원인 후보로 먼저 고를 만한 발견: 위험도 critical·high, 최대 limit건 */
export function urgentEvidence<T extends { finding: unknown }>(candidates: T[], limit = 10): T[] {
  const severity = (item: T) => (item.finding && typeof item.finding === "object" ? String((item.finding as Record<string, unknown>).severity ?? "") : "");
  return candidates.filter(item => ["critical", "high"].includes(severity(item))).slice(0, limit);
}

export function mergeActions(current: string, additions: string[]): string {
  const lines = current.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  for (const line of additions) if (!lines.includes(line)) lines.push(line);
  return lines.slice(0, 30).join("\n");
}

const notRequiredStatus = "신고 대상 아닐 수 있음";
export const heldStatus = "신고 대상 판단 보류 · 미확인 사실 있음";
/**
 * The API treats omitted yes/no answers as "no", so an unanswered privacy draft would say the filing criteria are not
 * met. Until the API accepts unknown answers, replace that conclusion with the questions that are still open.
 */
export function qualifyPrivacyDraft(report: FilingReport, markdown: string, gaps: string[]): { report: FilingReport; markdown: string } {
  if (report.kind !== "privacy_72h" || !gaps.length || !report.status.text.startsWith(notRequiredStatus)) return { report, markdown };
  const bullets = ["아직 확인하지 못한 사실이 있어 신고 대상인지 판단하지 않았습니다.", ...gaps,
    "확인한 뒤 초안을 다시 만들면 판단을 갱신합니다. 모르는 채로 기한이 다가오면 먼저 신고하는 편이 안전합니다."];
  const section = /^## 신고 대상인지\n\n(?:- .*\n)+/m;
  let next = markdown.replace(/^(\*\*상태\*\* )\S+ 신고 대상 아닐 수 있음 · 통지는 필요/m, `$1⚠️ ${heldStatus}`);
  next = section.test(next) ? next.replace(section, `## 신고 대상인지\n\n${bullets.map(line => `- ${line}`).join("\n")}\n`)
    : `> ${bullets.join(" ")}\n\n${next}`;
  return {
    report: { ...report, status: { text: heldStatus, tone: "warning" },
      sections: report.sections.map(item => item.heading === "신고 대상인지" ? { ...item, bullets } : item) },
    markdown: next,
  };
}
