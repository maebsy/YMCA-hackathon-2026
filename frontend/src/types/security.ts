export type OS = "windows" | "macos" | "linux";
export type TabType = "workspace" | "architecture" | "incident" | "report";
export type ReportType = "24h" | "72h";

export interface Finding {
  id: string;
  decision: "act" | "attend" | "trackstar";
  decisionLabel: string;
  title: string;
  file: string;
  verdict: string;
  verdictType: "ok" | "warn";
  confidence: string;
  scope: string;
  fixed: boolean;
  desc: string;
  redScenario: string;
  why: string[];
  commands: {
    windows: string;
    macos: string;
    linux: string;
  };
  aiPrompt: string;
  // 첫 번째 CWE 번호 (예: CWE-89). 실검증으로 재현할 수 있는 종류인지 고를 때 씁니다
  cwe?: string;
}

export interface LogItem {
  time: string;
  step: string;
  msg: string;
  status: string;
  type: "ok" | "warn";
}
