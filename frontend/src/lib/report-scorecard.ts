import type { Finding } from "@/types/security";

export const SCORE_LEVELS = {
  critical: { label: "CRIT 심각", short: "심각", rank: 0 },
  high: { label: "HIGH 높음", short: "높음", rank: 1 },
  medium: { label: "MED 중간", short: "중간", rank: 2 },
  low: { label: "LOW 낮음", short: "낮음", rank: 3 },
  info: { label: "INFO 참고", short: "참고", rank: 4 },
  unknown: { label: "— 확인 필요", short: "확인 필요", rank: 5 },
} as const;
export type ScoreLevel = keyof typeof SCORE_LEVELS;
export type ScoreRow = { id: string; severity: ScoreLevel; kind: string; rule: string; tool: string; location: string; fullLocation: string; title: string; action: string; priority: number; order: number };
const categories: Record<string, string> = { code: "코드", secret: "비밀키 노출", dependency: "외부 부품(라이브러리)", config: "설정" };
// Exact CWE identifiers only, never guess a vulnerability type from a title.
const cweNames: Record<string, string> = { "CWE-89": "SQL 인젝션", "CWE-79": "XSS", "CWE-798": "하드코딩 비밀값", "CWE-22": "경로 탐색", "CWE-78": "OS 명령 주입" };
const toolNames: Record<string, string> = { semgrep:"Semgrep", opengrep:"Semgrep", gitleaks:"Gitleaks", osv:"OSV-Scanner", "osv-scanner":"OSV-Scanner" };
const priorities = { act: 0, attend: 1, trackstar: 2 };
const text = (value: unknown) => typeof value === "string" && value.trim() ? value.trim() : "";
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }

export function scoreRows(raw: unknown[], findings: Finding[], pendingIds: string[]): ScoreRow[] {
  const source = raw.length ? raw : findings;
  return source.map((value, order) => {
    const item = record(value);
    const id = text(item.fingerprint) || text(item.id) || String(order);
    const display = findings.find(finding => finding.id === id);
    const severity = Object.hasOwn(SCORE_LEVELS, text(item.severity)) ? text(item.severity) as ScoreLevel : "unknown";
    const refs = record(item.refs);
    const cwe = Array.isArray(refs.cwe) ? refs.cwe.find(value => typeof value === "string" && cweNames[value]) : undefined;
    const category = text(item.category);
    const rule = text(item.rule_id);
    const kind = (typeof cwe === "string" ? cweNames[cwe] : categories[category] || category) || "—";
    const path = text(item.file_path);
    const line = typeof item.start_line === "number" && Number.isInteger(item.start_line) && item.start_line > 0 ? item.start_line : undefined;
    const action = display?.fixed || item.status === "code_resolved" ? "해결" : pendingIds.includes(id) ? "확인 중" : "";
    const tool = text(item.tool);
    const suffix = line ? ":" + line : "";
    return { id, severity, kind, rule: rule || "—", tool: toolNames[tool.toLowerCase()] || tool || "—",
      location: path ? path.split(/[\\/]/).at(-1) + suffix : "—", fullLocation: path ? path + suffix : "—",
      title: display?.title || text(item.title) || "—", action, priority: display ? priorities[display.decision] ?? 3 : 3, order };
  }).sort((a, b) => SCORE_LEVELS[a.severity].rank - SCORE_LEVELS[b.severity].rank || a.priority - b.priority || a.order - b.order);
}

// Memory only: refresh and back navigation show the completed scorecard immediately.
const played = new Set<string>();
export const hasScorecardAnimation = (identity: string) => played.has(identity);
export function claimScorecardAnimation(identity: string, fresh: boolean): boolean {
  if (!fresh || played.has(identity)) return false;
  played.add(identity);
  return true;
}
export const stampDuration = (count: number) => (Math.max(1, Math.min(count, 10)) - 1) * 210 + 450;
