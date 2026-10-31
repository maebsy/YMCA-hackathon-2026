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
}

export interface LogItem {
  time: string;
  step: string;
  msg: string;
  status: string;
  type: "ok" | "warn";
}
