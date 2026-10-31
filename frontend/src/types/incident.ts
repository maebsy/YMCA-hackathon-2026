export type FilingKind = "incident_24h" | "privacy_72h";
export type TriState = "unknown" | "yes" | "no";
export type IncidentType = "hacking" | "malware" | "ddos" | "defacement" | "account_takeover" | "data_leak" | "other";

export type IncidentForm = {
  organizationName: string;
  serviceName: string;
  discoveredAt: string;
  occurredAt: string;
  summary: string;
  cause: string;
  damage: string;
  actions: string;
  department: string;
  contactName: string;
  contactPhone: string;
  contactEmail: string;
  incidentTypes: IncidentType[];
  incidentStatus: "unknown" | "ongoing" | "contained" | "recovered";
  filingType: "unknown" | "initial" | "supplement";
  leakState: "unknown" | "none" | "suspected" | "confirmed";
  affectedCount: string;
  countIsEstimate: boolean;
  personalItems: string;
  includesSensitive: TriState;
  includesUniqueId: TriState;
  externalAccess: TriState;
  recoveredLowRisk: TriState;
  subjectsNotified: TriState;
  notifyMethod: string;
  notifiedAt: string;
};

export type PersonalInfoBreach = {
  leaked: "none" | "suspected" | "confirmed";
  affected_count?: number | null;
  count_is_estimate?: boolean;
  items?: string[];
  includes_sensitive?: boolean;
  includes_unique_id?: boolean;
  external_unauthorized_access?: boolean;
  recovered_low_risk?: boolean;
  subjects_notified?: boolean;
  notified_at?: string | null;
  notify_method?: string | null;
  subject_mitigations?: string[];
  relief_procedure?: string | null;
  damage_report_contact?: string | null;
};

export type IncidentInput = {
  organization: {
    name?: string | null;
    service_name?: string | null;
    service_url?: string | null;
    department?: string | null;
    contact_name?: string | null;
    contact_phone?: string | null;
    contact_email?: string | null;
  };
  discovered_at: string;
  occurred_at?: string | null;
  incident_types: IncidentType[];
  summary?: string | null;
  cause?: string | null;
  damage?: string | null;
  affected_systems?: string[];
  actions_taken: { at?: string | null; action: string }[];
  status?: "ongoing" | "contained" | "recovered";
  is_supplement?: boolean;
  related_fingerprints: string[];
  personal_info: PersonalInfoBreach | null;
};

export type FilingFinding = Record<string, unknown> & {
  fingerprint: string;
  tool: string;
  category: "dependency" | "code" | "secret" | "config";
  rule_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low" | "info" | "unknown";
};
export type FilingRequest = { incident: IncidentInput; findings: FilingFinding[] };

export type ReportBadge = { text: string; tone: "danger" | "warning" | "ok" | "info" | "muted" };
export type ReportField = { label: string; value: string | null; required: boolean; hint?: string | null; auto: boolean };
export type ReportCard = { title: string; badges: ReportBadge[]; paragraphs: string[]; fields: ReportField[]; steps: string[] };
export type ReportSection = { heading: string; paragraphs: string[]; fields: ReportField[]; bullets: string[]; steps: string[]; cards: ReportCard[] };
export type Deadline = {
  label: string;
  basis: string;
  starts_at: string;
  due_at: string;
  hours: number;
  remaining_minutes: number;
  overdue: boolean;
  stopped_at?: string | null;
};
export type FilingNeed = { kind: FilingKind; required: boolean; reasons: string[]; deadline?: Deadline | null };
export type AssessResponse = { needs: FilingNeed[] };
export type FilingReport = {
  kind: FilingKind;
  title: string;
  subtitle?: string | null;
  generated_at: string;
  status: ReportBadge;
  deadline?: Deadline | null;
  sections: ReportSection[];
  missing: string[];
  submit_to: string[];
  disclaimer?: string | null;
};
