// 웹 검사 결과 → MCP 전달 (integrations/mcp-handoff).
// MCP 서버는 `/api/llm/explain` 응답 형식의 JSON 파일을 읽습니다. 파일 안 `source`에 검사 대상 저장소·커밋·시각을
// 넣어 두면 서버를 `--revision` 없이 띄웠을 때 호출마다 최신 파일을 읽습니다(재검사해도 설정·재시작 불필요).
// 파일 이름은 저장소별로 고정해 같은 저장소를 다시 검사하면 같은 파일을 덮어씁니다.
// 전달 조건은 서버(handoff.py `_reason`)와 같게 계산해 화면의 "전달 가능 N건"이 서버 동작과 어긋나지 않게 합니다.
import type { OS } from "@/types/security";

/* eslint-disable @typescript-eslint/no-explicit-any */

const MAX_RESULTS = 50; // handoff.py MAX_RESULTS
const MAX_PROMPT = 2000; // handoff.py MAX_PROMPT

export type BlockReason =
  | "explanation_failed"
  | "invalid_explanation"
  | "red_not_passed"
  | "inconsistent_red_review"
  | "manual_review_required"
  | "false_positive_review_required"
  | "invalid_prompt"
  | "missing_provenance";

export const BLOCK_LABEL: Record<BlockReason, string> = {
  explanation_failed: "해석 실패·건너뜀",
  invalid_explanation: "해석 형식 오류",
  red_not_passed: "Red 검증 미통과",
  inconsistent_red_review: "Red 판정 기록 불일치",
  manual_review_required: "사람 확인 필요",
  false_positive_review_required: "오탐 의심",
  invalid_prompt: "수정 지시 없음",
  missing_provenance: "모델 정보 없음",
};

/** MCP 서버가 이 결과의 수정 지시를 막는 이유. 전달 가능하면 null */
export function blockReason(result: any): BlockReason | null {
  if (result?.status !== "done") return "explanation_failed";
  const e = result.explanation;
  if (!e || typeof e !== "object" || e.fingerprint !== result.fingerprint) return "invalid_explanation";
  if (e.variant !== "D" || e.red_verdict !== "pass") return "red_not_passed";
  const rounds = e.red_rounds;
  const last = Array.isArray(rounds) && rounds.length ? rounds[rounds.length - 1] : null;
  if (!last || typeof last !== "object" || last.verdict !== "pass" || !Array.isArray(last.issues) || last.issues.length)
    return "inconsistent_red_review";
  if (e.needs_manual_review !== false) return "manual_review_required";
  if (e.false_positive_suspect !== false) return "false_positive_review_required";
  const prompt = e.ai_fix_prompt;
  if (typeof prompt !== "string" || !prompt.trim() || prompt.length > MAX_PROMPT) return "invalid_prompt";
  for (const key of ["model", "prompt_version"]) {
    const v = e[key];
    if (typeof v !== "string" || v.trim().length < 1 || v.trim().length > 200) return "missing_provenance";
  }
  return null;
}

/** https://github.com/owner/repo(.git)(/) → owner/repo. 서버와 같은 형식만 허용 */
export function repositoryOf(repoUrl: unknown): string | null {
  if (typeof repoUrl !== "string") return null;
  const m = repoUrl.trim().match(/^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/);
  return m ? `${m[1]}/${m[2]}` : null;
}

export type Handoff =
  | { ok: false; why: string }
  | {
      ok: true;
      repository: string;
      revision: string;
      fileName: string;
      snapshot: {
        mode: "red_blue";
        source: { repository: string; revision: string; generated_at: string; tool: "72hours-web" };
        results: any[];
      };
      ready: number;
      blocked: { reason: BlockReason; count: number }[];
    };

/**
 * 마지막 검사(브라우저에 저장된 `saveLast` 값)로 MCP 전달 자료를 만듭니다.
 * last = { repoUrl, result: 엔진 결과, reportInput: { explain_results } }
 */
export function buildHandoff(last: any): Handoff {
  if (!last) return { ok: false, why: "아직 검사 결과가 없습니다. 먼저 저장소를 검사하세요." };
  const repository = repositoryOf(last.result?.target?.repo_url ?? last.repoUrl);
  if (!repository) return { ok: false, why: "검사 대상이 공개 GitHub 저장소 주소가 아닙니다." };
  const revision = String(last.result?.target?.commit_sha ?? "");
  if (!/^[0-9a-fA-F]{40}$/.test(revision))
    return { ok: false, why: "검사한 커밋(40자리 SHA)을 알 수 없습니다. 다시 검사해 주세요." };
  const results: any[] = Array.isArray(last.reportInput?.explain_results) ? last.reportInput.explain_results : [];
  if (!results.length)
    // 결과 화면은 해석이 끝나기 전에 열립니다(#144). 'GPU가 꺼져 있다'로 읽히지 않게 진행 중일 수 있음을 먼저 말합니다
    return { ok: false, why: "아직 Red–Blue 해석이 끝난 항목이 없습니다. 해석이 진행 중이면 끝나는 대로 여기서 전달할 수 있습니다. 해석 서버가 꺼져 있으면 만들어지지 않습니다." };
  // 서버는 1~50건, fingerprint 중복을 거부합니다
  const seen = new Set<string>();
  const unique = results.filter((r) => typeof r?.fingerprint === "string" && !seen.has(r.fingerprint) && seen.add(r.fingerprint));
  const picked = unique.slice(0, MAX_RESULTS);
  const counts = new Map<BlockReason, number>();
  let ready = 0;
  for (const r of picked) {
    const why = blockReason(r);
    if (why) counts.set(why, (counts.get(why) ?? 0) + 1);
    else ready += 1;
  }
  const [owner, repo] = repository.split("/");
  const rev = revision.toLowerCase();
  // 검사 시각이 있으면 그 값을, 없으면 지금 시각을 씁니다 (MCP list_findings 의 source.generated_at)
  const scannedAt = last.result?.scanned_at ?? last.reportInput?.scan?.scanned_at;
  const generatedAt = typeof scannedAt === "string" && scannedAt.length <= 40 ? scannedAt : new Date().toISOString();
  return {
    ok: true,
    repository,
    revision: rev,
    fileName: `72hours-mcp-${owner}-${repo}.json`,
    snapshot: {
      mode: "red_blue",
      source: { repository, revision: rev, generated_at: generatedAt, tool: "72hours-web" },
      results: picked,
    },
    ready,
    blocked: [...counts].map(([reason, count]) => ({ reason, count })),
  };
}

const PATHS: Record<OS, { python: string; server: string; download: (f: string) => string }> = {
  windows: {
    python: "C:/absolute/path/to/mcp-handoff/.venv/Scripts/python.exe",
    server: "C:/absolute/path/to/mcp-handoff/server.py",
    download: (f) => `C:/Users/<사용자>/Downloads/${f}`,
  },
  macos: {
    python: "/absolute/path/to/mcp-handoff/.venv/bin/python",
    server: "/absolute/path/to/mcp-handoff/server.py",
    download: (f) => `/Users/<사용자>/Downloads/${f}`,
  },
  linux: {
    python: "/absolute/path/to/mcp-handoff/.venv/bin/python",
    server: "/absolute/path/to/mcp-handoff/server.py",
    download: (f) => `/home/<사용자>/Downloads/${f}`,
  },
};

/**
 * client.example.json 과 같은 `mcpServers` 설정 (최초 1회만 붙여 넣기).
 * `--revision` 없이 띄워 MCP가 호출마다 최신 파일을 읽게 하고, `--repository`로 저장소를 고정합니다.
 */
export function clientConfig(h: Extract<Handoff, { ok: true }>, os: OS): string {
  const p = PATHS[os];
  return JSON.stringify(
    {
      mcpServers: {
        "72hours-handoff": {
          command: p.python,
          args: [p.server, "--results", p.download(h.fileName), "--repository", h.repository],
          env: { PYTHONIOENCODING: "utf-8" },
        },
      },
    },
    null,
    2,
  );
}
