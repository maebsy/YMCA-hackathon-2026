"use client";

import { useEffect, useRef, useState } from "react";
import { CircleCheck, CircleQuestionMark, CircleX, FlaskConical, LoaderCircle, Play, RotateCcw, Sparkles } from "lucide-react";
import { attackVerdictLabels, isolationLabels, requestLine, runVerify, testsLabel, attemptsLine, verdictHelp, verdictLabels, type AttackDefinition, type AttackOutcome, type VerifyJob, type VerifyMode } from "@/lib/verify";

type Phase = "idle" | "queued" | "running" | "done" | "error";
const phaseText: Partial<Record<Phase, string>> = {
  queued: "실검증을 접수했습니다. 순서를 기다리는 중입니다…",
  running: "격리 환경에서 수정 전·후 앱을 띄워 공격하고 기능 테스트를 돌리는 중입니다…",
};
const aiRunning = "GPU의 Red가 공격을, Blue가 수정본을 만들고 Docker 격리 환경에서 수정 전·후를 실행하는 중입니다…";

function Side({ label, succeeded, status, evidence }: { label: string; succeeded: boolean; status: number | null; evidence: string | null }) {
  return <div className="vp-side" data-hit={succeeded}>
    <p className="vp-side-head"><span>{label}</span><strong>{succeeded ? "공격 성공" : "공격 막힘"}</strong>{status ? <small>HTTP {status}</small> : null}</p>
    {evidence && <pre className="vp-evidence" tabIndex={0}>{evidence}</pre>}
  </div>;
}

function AttackRow({ outcome, def, reason }: { outcome: AttackOutcome; def?: AttackDefinition; reason?: string }) {
  return <li className="vp-attack">
    <div className="vp-attack-head">
      <strong>{outcome.id}</strong>{def?.cwe && <span className="vp-chip">{def.cwe}</span>}
      <span className="vp-chip" data-tone={outcome.verdict === "verified" ? "ok" : outcome.verdict === "fix_failed" ? "danger" : "warn"}>{attackVerdictLabels[outcome.verdict]}</span>
    </div>
    {def?.request && <p className="vp-request"><span className="vp-muted">보낸 공격</span><code>{requestLine(def.request)}</code></p>}
    <div className="vp-sides">
      <Side label="수정 전" succeeded={outcome.before_succeeded} status={outcome.before_status} evidence={outcome.before_evidence}/>
      <Side label="수정 후" succeeded={outcome.after_succeeded} status={outcome.after_status} evidence={outcome.after_evidence}/>
    </div>
    {def?.note && <p className="vp-note">{def.note}</p>}
    {reason && <p className="vp-note"><span className="vp-muted">Red가 이 공격을 고른 이유 · </span>{reason}</p>}
  </li>;
}

function DiffView({ diff }: { diff: string }) {
  return <pre className="vp-diff" tabIndex={0}>{diff.split("\n").map((line, i) => {
    const kind = line.startsWith("@@") ? "hunk" : line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : undefined;
    return <span key={i} data-line={kind}>{line}{"\n"}</span>;
  })}</pre>;
}

function Result({ job }: { job: VerifyJob }) {
  const result = job.result!;
  const verdict = verdictLabels[result.status];
  const defs = new Map(job.attacks.map(a => [a.id, a]));
  const staticOnly = job.attacks.filter(a => a.runtime === false);
  return <div className="vp-result">
    <div className="vp-verdict" data-tone={verdict.tone} role="status">
      <p className="vp-verdict-label">판정 · {verdict.label}</p>
      <p>{result.message}</p>
      {verdictHelp(job).map(line => <p key={line} className="vp-help">{line}</p>)}
      <p className="vp-muted">실행 환경: {result.sandbox === "docker" ? "Docker 격리 컨테이너" : "이 서버에서 바로 실행 (데모 과녁 전용)"} · {result.duration_sec}초</p>
      <p className="vp-muted">수정본: {job.mode === "ai" ? "GPU Red·Blue가 만든 공격과 수정본 (사람이 최종 확인 필요)" : "사람이 쓴 기준 수정본"}</p>
      {job.mode === "ai" && attemptsLine(job.ai) && <p className="vp-note"><span className="vp-muted">AI 수정 시도 · </span>{attemptsLine(job.ai)} (실패한 실행 결과를 Blue에게 돌려주고 다시 고쳤습니다)</p>}
      {job.mode === "ai" && job.ai && Object.values(job.ai.patch_summaries).map((s, i) => <p key={i} className="vp-note"><span className="vp-muted">Blue 수정 요약 · </span>{s}</p>)}
      {job.mode === "ai" && job.ai && job.ai.skipped.length > 0 && <ul className="vp-note">{job.ai.skipped.map((s, i) => <li key={i}>건너뜀({s.stage}) {s.fingerprint}: {s.reason}</li>)}</ul>}
      {job.reused && <p className="vp-reused">최근 실행 결과입니다{job.finished_at && <> (<time dateTime={job.finished_at}>{new Date(job.finished_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time> 실행)</>}. 데모 입력이 고정이라 잠시 동안은 다시 실행하지 않고 같은 결과를 보여 줍니다.</p>}
    </div>

    {result.attacks.length > 0 && <section aria-labelledby="verify-attacks">
      <h3 id="verify-attacks" className="vp-h3">공격별 수정 전 / 수정 후</h3>
      <ul className="vp-attacks">{result.attacks.map(o => <AttackRow key={o.id} outcome={o} def={defs.get(o.id)} reason={job.ai?.red_reasons[o.id]}/>)}</ul>
    </section>}

    <section aria-labelledby="verify-tests">
      <h3 id="verify-tests" className="vp-h3">기능 테스트</h3>
      <dl className="vp-tests">
        <div><dt>수정 전</dt><dd>{testsLabel(result.before_tests)}</dd></div>
        <div><dt>수정 후</dt><dd data-tone={result.after_tests.ok === false ? "danger" : result.after_tests.ok ? "ok" : undefined}>{testsLabel(result.after_tests)}</dd></div>
      </dl>
      <p className="vp-note">수정 후에도 기능 테스트가 통과해야 &lsquo;고치면서 기능은 그대로&rsquo;라고 판단합니다.</p>
    </section>

    <section aria-labelledby="verify-isolation">
      <h3 id="verify-isolation" className="vp-h3">격리 확인 <small className="vp-muted">샌드박스 안에서 직접 읽은 값</small></h3>
      <ul className="vp-isolation">{isolationLabels.map(([key, label]) => {
        const value = result.isolation[key];
        return <li key={key} data-state={value === true ? "yes" : value === false ? "no" : "unknown"}>
          {value === true ? <CircleCheck size={16} aria-hidden/> : value === false ? <CircleX size={16} aria-hidden/> : <CircleQuestionMark size={16} aria-hidden/>}
          <span>{label}</span><small>{value === true ? "확인됨" : value === false ? "아님" : "모름"}</small>
        </li>;
      })}</ul>
      <p className="vp-note">{result.isolation_confirmed
        ? "네 항목 모두 수정 전·후 실행에서 확인했습니다."
        : "데모 과녁은 우리가 만든 코드라 Docker가 없는 서버에서는 격리 없이 실행합니다. 그래서 위 항목이 확인되지 않을 수 있습니다. 사용자 저장소는 Docker 격리가 네 항목 모두 확인될 때만 판정을 냅니다."}</p>
    </section>

    {staticOnly.length > 0 && <section aria-labelledby="verify-static">
      <h3 id="verify-static" className="vp-h3">실행으로 확인하지 않는 항목</h3>
      <ul className="vp-static">{staticOnly.map(a => <li key={a.id}><strong>{a.id}</strong>{a.cwe && <span className="vp-chip">{a.cwe}</span>}{a.note && <p className="vp-note">{a.note}</p>}</li>)}</ul>
    </section>}

    {job.patch_diff && <details className="vp-details">
      <summary>수정 내용 보기 ({job.patched_files.join(", ")})</summary>
      <DiffView diff={job.patch_diff}/>
    </details>}
  </div>;
}

export default function VerifyPanel() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<VerifyJob | null>(null);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const run = useRef(0);
  const busy = phase === "queued" || phase === "running";

  useEffect(() => () => { run.current++; }, []);
  // 취약점 상세의 '실검증으로 확인하기'(/verify?run=reference)로 들어오면 바로 실행합니다. 한 번만 실행하고 주소에서 지웁니다
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("run");
    if (requested !== "reference" && requested !== "ai") return;
    // Next.js가 쓰는 history state(__NA 등)는 그대로 두고 주소의 ?run=만 지웁니다
    window.history.replaceState(window.history.state, "", window.location.pathname);
    const timer = window.setTimeout(() => { void start(requested); }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  const [mode, setMode] = useState<VerifyMode>("reference");

  async function start(next: VerifyMode) {
    if (busy) return;
    const token = ++run.current;
    setMode(next); setPhase("queued"); setError(""); setElapsed(0);
    try {
      const done = await runVerify({ mode: next, onStatus: s => { if (token === run.current) setPhase(s === "running" ? "running" : "queued"); }, isCancelled: () => token !== run.current });
      if (token !== run.current) return;
      setJob(done); setPhase("done");
    } catch (caught) {
      if (token !== run.current) return;
      setError(caught instanceof Error ? caught.message : "실검증을 실행하지 못했습니다.");
      setPhase("error");
    }
  }

  return <section className="vp-panel" aria-labelledby="verify-title">
    <div className="vp-head">
      <FlaskConical size={22} aria-hidden className="vp-accent"/>
      <h2 id="verify-title">Red–Blue 실검증 · 데모 과녁</h2>
    </div>
    <p className="vp-muted">일부러 취약하게 만든 작은 사이트(<code>demo-vulnerable-site</code>)를 수정 전·후 두 번 띄워 같은 공격을 보냅니다. 수정 전에는 공격이 통하고, 수정 후에는 막히며, 기능 테스트는 그대로 통과하는지 실제 실행 결과로 확인합니다.</p>
    <div className="vp-actions">
      <button type="button" className="vp-button" onClick={() => void start("reference")} disabled={busy}>
        {busy && mode === "reference" ? <LoaderCircle size={16} className="vp-spin" aria-hidden/> : job?.mode === "reference" ? <RotateCcw size={16} aria-hidden/> : <Play size={16} aria-hidden/>}
        {busy && mode === "reference" ? "실검증 진행 중" : "기준 수정본으로 실행"}
      </button>
      <button type="button" className="vp-button" onClick={() => void start("ai")} disabled={busy}>
        {busy && mode === "ai" ? <LoaderCircle size={16} className="vp-spin" aria-hidden/> : <Sparkles size={16} aria-hidden/>}
        {busy && mode === "ai" ? "AI 실검증 진행 중" : "AI(Red·Blue) 수정본으로 실행"}
      </button>
      <p className="vp-status" role="status">{busy ? `${phase === "running" && mode === "ai" ? aiRunning : phaseText[phase]} ${elapsed}초` : ""}</p>
    </div>
    {error && <p className="vp-error" role="alert">{error}</p>}
    {job?.result && <Result job={job}/>}
  </section>;
}
