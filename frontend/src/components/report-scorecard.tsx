"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Flame, Info, RotateCcw, Siren, TriangleAlert } from "lucide-react";
import { claimScorecardAnimation, hasScorecardAnimation, SCORE_LEVELS, stampDuration, type ScoreLevel, type ScoreRow } from "@/lib/report-scorecard";
import "./report-scorecard.css";

const icons = { critical:Siren, high:Flame, medium:TriangleAlert, low:Info, info:Info, unknown:Info };

function Row({ row, index, animated }: { row: ScoreRow; index: number; animated: boolean }) {
  const Icon = icons[row.severity];
  return <li className={`score-row score-${row.severity}${animated ? " score-stamp" : ""}`} style={{ "--stamp-index":index } as CSSProperties}>
    <div className="score-primary">
      <span className="score-icon"><Icon size={17} aria-hidden="true"/></span>
      <span className="score-grade"><span>{SCORE_LEVELS[row.severity].label}</span></span>
      <strong className="score-title" title={row.kind}>{row.kind}</strong>
    </div>
    <div className="score-secondary">
      <span className="score-detail" title={row.title}>{row.title}</span>
      <span className="score-detail" title={row.rule}>{row.rule}</span>
      <span className="score-detail" title={row.tool}>{row.tool}</span>
      <span className="score-location" title={row.fullLocation}>{row.location}</span>
      {row.action && <span className="score-detail">{row.action}</span>}
    </div>
  </li>;
}

export default function ReportScorecard({ rows, identity, fresh, children }: { rows: ScoreRow[]; identity: string; fresh: boolean; children: ReactNode }) {
  const initialPlayback = fresh && !hasScorecardAnimation(identity);
  const [run, setRun] = useState(0);
  const [animating, setAnimating] = useState(initialPlayback);
  const [open, setOpen] = useState(!initialPlayback);
  const [announcement, setAnnouncement] = useState("");
  const pendingPlayback = useRef<boolean | undefined>(undefined);
  const summary = (Object.keys(SCORE_LEVELS) as ScoreLevel[]).map(level => `${SCORE_LEVELS[level].short} ${rows.filter(row => row.severity === level).length}건`).join(", ");
  useEffect(() => {
    // Keep a pending claim through Strict Mode effect cleanup; cancel timers on unmount.
    if (pendingPlayback.current === undefined) pendingPlayback.current = claimScorecardAnimation(identity, fresh);
    if (!pendingPlayback.current) return;
    const timer = setTimeout(() => {
      pendingPlayback.current = false;
      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setAnimating(true); setOpen(false); setRun(value => value + 1);
      } else { setAnimating(false); setOpen(true); setAnnouncement(summary); }
    }, 0);
    return () => clearTimeout(timer);
  }, [identity, fresh, summary]);
  useEffect(() => {
    if (!animating) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finish = () => { setAnimating(false); setOpen(true); setAnnouncement(summary); };
    const timer = setTimeout(finish, stampDuration(rows.length));
    const changed = () => { if (query.matches) finish(); };
    query.addEventListener("change", changed);
    return () => { clearTimeout(timer); query.removeEventListener("change", changed); };
  }, [animating, run, rows.length, summary]);
  function replay() {
    setAnnouncement("");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setOpen(true); setAnnouncement(summary); return; }
    setOpen(false); setAnimating(true); setRun(value => value + 1);
  }
  return <>
    <section className="scorecard" aria-labelledby="scorecard-title">
      <div className="score-heading"><h1 id="scorecard-title">검사 채점표</h1><button type="button" onClick={replay}><RotateCcw size={12} aria-hidden="true"/>다시 재생</button></div>
      <div className="score-totals" aria-label="등급별 발견 건수">{(Object.keys(SCORE_LEVELS) as ScoreLevel[]).filter(level => SCORE_LEVELS[level].rank < 4 || rows.some(row => row.severity === level)).map(level => <span className={`score-total score-${level}`} key={level}>{SCORE_LEVELS[level].short} <b>{rows.filter(row => row.severity === level).length}</b></span>)}</div>
      {rows.length ? <ul className="score-list" aria-label="심각도별 발견 항목" key={run}>{rows.slice(0,10).map((row,index) => <Row key={row.id} row={row} index={index} animated={animating}/>)}</ul> : <div key={run} className={`score-empty${animating ? " score-stamp" : ""}`} style={{ "--stamp-index":0 } as CSSProperties}><Info size={19} aria-hidden="true"/><b>발견 0건</b><span>검사 범위 밖의 안전을 보장하지 않습니다.</span></div>}
      {rows.length > 10 && <details className="score-more"><summary>외 {rows.length - 10}건</summary><ul className="score-list" aria-label="나머지 발견 항목">{rows.slice(10).map(row => <Row key={row.id} row={row} index={0} animated={false}/>)}</ul></details>}
      <p className="score-sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    </section>
    <div className="score-document-heading"><button type="button" aria-expanded={open} aria-controls="score-document" onClick={() => setOpen(value => !value)}>{open ? "리포트 접기" : "리포트 펼치기"}</button></div>
    <div id="score-document" className={`score-document${open ? " score-document-open" : ""}`} inert={!open}><div className="score-document-inner">{children}</div></div>
  </>;
}
