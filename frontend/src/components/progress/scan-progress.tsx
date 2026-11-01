"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { Check, LoaderCircle, TriangleAlert } from "lucide-react";

export type ProgressProps = {
  repo: string;
  phase: "idle" | "queued" | "running" | "explaining" | "reporting" | "done" | "failed";
  startedAt?: number;
  logs: string[];
  explained?: { done: number; total: number; running?: number; queued?: number };
  counts?: { total: number; open: number };
  error?: string;
  onRetry?: () => void;
  reportFailed?: boolean; resultHref?: string; busy?: boolean;
};

const labels = { idle: "준비", queued: "접수 대기", running: "점검 중", explaining: "AI 분석 중", reporting: "리포트 정리 중", done: "완료", failed: "중단됨" };
const steps = [
  { title: "접수", description: "요청을 확인합니다." },
  { title: "점검", description: "비밀키·코드·부품·설정을 살핍니다." },
  { title: "AI 분석", description: "위험한 항목부터 풀어 설명합니다." },
  { title: "리포트", description: "근거와 고칠 순서를 정리합니다." },
];
/** "완료 1/5 · 해석 중 2 · 대기 2". 해석 중·대기 건수는 상태를 받기 전이면 생략합니다. */
export function explainedText(explained: { done: number; total: number; running?: number; queued?: number }): string {
  const parts = [`완료 ${explained.done}/${explained.total}건`];
  if (explained.running) parts.push(`해석 중 ${explained.running}`);
  if (explained.queued && explained.done < explained.total) parts.push(`대기 ${explained.queued}`);
  return parts.join(" · ");
}

const mobileQuery = "(max-width: 720px)";
function subscribeMobile(notify: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}

function Elapsed({ startedAt, active }: { startedAt?: number; active: boolean }) {
  const [clock, setClock] = useState<{ start: number; now: number }>();
  useEffect(() => {
    if (startedAt === undefined) return;
    const tick = () => setClock({ start: startedAt, now: Date.now() });
    const first = window.setTimeout(tick, 0);
    const timer = active ? window.setInterval(tick, 1000) : undefined;
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [startedAt, active]);
  const seconds = startedAt === undefined || clock?.start !== startedAt ? undefined : Math.max(0, Math.floor((clock.now - startedAt) / 1000));
  return <span className="ph-elapsed" aria-live="off">경과 시간 <b>{seconds === undefined ? "—" : `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`}</b></span>;
}

export default function ProgressH({ repo, phase, startedAt, logs, explained, counts, error, onRetry, reportFailed, resultHref, busy }: ProgressProps) {
  const [expanded, setExpanded] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [follow, setFollow] = useState(true);
  const [pausedRange, setPausedRange] = useState<{ start: number; end: number } | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const mobile = useSyncExternalStore(subscribeMobile, () => window.matchMedia(mobileQuery).matches, () => false);
  const recentLines = mobile ? 4 : 8;
  const active = !!busy || phase === "queued" || phase === "running" || phase === "explaining" || phase === "reporting";
  const start = showAll ? 0 : pausedRange?.start ?? Math.max(0, logs.length - recentLines);
  const end = showAll ? logs.length : pausedRange?.end ?? logs.length;
  const visible = logs.slice(start, end);
  useEffect(() => {
    if (expanded && follow && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [logs, expanded, follow, showAll, mobile]);

  // Report failures are explicit; infer earlier failures only from the supplied records.
  const failureStep = reportFailed ? 3 : explained || logs.some(line => /LLM|해석/.test(line)) ? 2
    : counts ? 3 : logs.some(line => /엔진 상태:\s*(running|done)|엔진 검사 중/.test(line)) ? 1
    : logs.some(line => /엔진 상태:\s*queued|접수/.test(line)) ? 0 : -1;
  const current = phase === "failed" ? failureStep : ({ idle: -1, queued: 0, running: 1, explaining: 2, reporting: 3, done: 3 } as const)[phase];
  const failure = <div className="ph-error"><p>{error || "검사 요청을 완료하지 못했습니다."}</p>{onRetry && <button className="ph-button ph-retry" type="button" onClick={onRetry}>{reportFailed ? "다시 만들기" : "다시 시도"}</button>}{reportFailed && resultHref && <Link className="ph-text-button" href={resultHref}>결과만 보기</Link>}</div>;

  function latest() { setPausedRange(null); setFollow(true); }
  return <section className={`ph-progress ph-phase-${phase}`} aria-label="단계와 로그로 보는 검사 진행">
    <p className="ph-sr-only" role="status" aria-live="polite" aria-atomic="true">{labels[phase]}</p>
    <div className="ph-summary"><code className="ph-repo">{repo}</code><span className="ph-state"><span className={`ph-dot${active ? " ph-pulse" : ""}`} aria-hidden="true"/>{labels[phase]}</span><Elapsed startedAt={startedAt} active={active}/></div>
    <div className="ph-columns">
      <div className="ph-stages"><div className="ph-section-heading"><h2 className="ph-section-title">진행 단계</h2>{onRetry && !reportFailed && <button className="ph-text-button" type="button" disabled={active || phase === "idle"} onClick={onRetry}>재검사</button>}</div>
        <ol className="ph-step-list" aria-label="검사 단계">{steps.map((step, index) => {
          const noExplanationCount = index === 2 && (phase === "done" || phase === "reporting" || reportFailed) && !explained;
          const skipped = noExplanationCount && logs.some(line => /해석 없음|해석 서버에 연결할 수 없어/.test(line));
          const complete = phase === "done" || (current >= 0 && index < current);
          const selected = phase !== "idle" && index === current;
          const failed = selected && phase === "failed";
          return <li key={step.title} className={`ph-step${complete ? " ph-step-done" : ""}${selected ? " ph-step-current" : ""}${failed ? " ph-step-failed" : ""}`} aria-current={selected ? "step" : undefined}>
            <div className="ph-step-track"><span className="ph-marker" aria-hidden="true">{failed ? <TriangleAlert size={16}/> : noExplanationCount ? "—" : complete ? <Check size={16}/> : selected ? <LoaderCircle className="ph-spinner" size={16}/> : `0${index + 1}`}</span></div>
            <div className="ph-step-copy"><div className="ph-step-heading"><h3 className="ph-step-title">{step.title}</h3><span className="ph-step-state">{noExplanationCount ? skipped ? "건너뜀(연결 안 됨)" : "기록 확인" : complete ? "완료" : failed ? "중단" : selected ? "진행 중" : "대기"}</span></div><p className="ph-step-description">{noExplanationCount ? skipped ? "추가 해석 없이 엔진 결과를 표시합니다." : "추가 해석 여부는 검사 기록에서 확인하세요." : step.description}</p>{index === 2 && explained && <p className="ph-explained">{explainedText(explained)}</p>}{failed && failure}</div>
          </li>;
        })}</ol>
        <div className="ph-outcome">
          {phase === "failed" && failureStep < 0 ? failure : phase === "done" && counts ? <div className="ph-results"><p>전체 <strong>{counts.total}건</strong><span className="ph-result-divider">·</span>미해결 <strong>{counts.open}건</strong></p><p className="ph-results-note">검사 범위와 근거를 함께 확인하세요.</p></div> : <p className="ph-stage-note">{phase === "running" ? "엔진 검사는 보통 1~3분 걸립니다." : phase === "reporting" ? "HTML과 Markdown 리포트를 만들고 있습니다." : phase === "explaining" ? "완료된 해석부터 결과에 반영합니다." : phase === "done" ? "검사 범위와 근거를 함께 확인하세요." : phase === "failed" ? "오류를 확인한 뒤 다시 시도해 주세요." : "검사 요청의 응답을 기다립니다."}</p>}
        </div>
      </div>
      <div className="ph-console"><div className="ph-console-heading"><h2 className="ph-section-title"><span className="ph-prompt" aria-hidden="true">&gt;_</span> 검사 진행 기록</h2><button className="ph-text-button" type="button" aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded(value => !value)}>{expanded ? "접기 −" : "펼치기 +"}</button></div>
        <div className="ph-console-body" id={panelId} hidden={!expanded} aria-live="off">
          <div className="ph-log-meta"><span>{showAll ? `전체 ${logs.length}줄` : `기록 ${visible.length}줄 · 전체 ${logs.length}줄`}</span><span>기록된 시각</span></div>
          <div className="ph-log-viewport" ref={viewport} role="region" aria-label="검사 로그, 위아래로 스크롤할 수 있습니다" tabIndex={0} onScroll={event => {
            const element = event.currentTarget;
            const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 20;
            if (!atBottom && follow) { setFollow(false); if (!showAll) setPausedRange({ start, end }); }
            else if (atBottom && !follow) latest();
          }}>
            {logs.length === 0 ? <p className="ph-empty">검사를 시작하면 받은 기록이 여기에 표시됩니다.</p> : <ol className="ph-log-list" start={start + 1}>{visible.map((line, index) => {
              const match = /^(?:\[(\d{2}:\d{2}:\d{2})\]|(\d{2}:\d{2}:\d{2}))\s+([\s\S]*)$/.exec(line);
              return <li className="ph-log-line" key={`${start + index}-${line}`}><span className="ph-line-number" aria-hidden="true">{String(start + index + 1).padStart(2, "0")}</span><span className="ph-log-time" aria-label={match ? undefined : "기록 시각 없음"}>{match ? match[1] ?? match[2] : "—"}</span><span className="ph-log-message">{match ? match[3] : line}</span></li>;
            })}</ol>}
          </div>
          <div className="ph-log-actions"><span className="ph-follow-label">{follow ? active ? "새 기록을 기다립니다" : "현재까지 받은 기록" : "이전 기록을 보고 있습니다"}</span><div className="ph-action-group">{!follow && <button className="ph-text-button" type="button" onClick={latest}>최신으로 ↓</button>}{logs.length > recentLines && <button className="ph-text-button" type="button" aria-pressed={showAll} onClick={() => { setShowAll(value => !value); setPausedRange(null); setFollow(true); }}>{showAll ? `최근 ${recentLines}줄만` : "전체 보기"}</button>}</div></div>
        </div>
        {!expanded && <p className="ph-collapsed-note">기록 {logs.length}줄 · 펼치면 진행 기록을 확인할 수 있습니다.</p>}
      </div>
    </div>
  </section>;
}
