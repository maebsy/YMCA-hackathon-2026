import type { FilingFinding, FilingKind, FilingRequest, IncidentForm, IncidentInput, IncidentType, PersonalInfoBreach } from "@/types/incident";

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
    if (form.externalAccess === "unknown") gaps.push("외부의 불법 접근 여부를 아직 확인하지 않았습니다.");
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
