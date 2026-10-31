"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Check, CheckCheck, ChevronRight, CircleHelp, Clipboard, Code2, Download, FileText, Globe2, LoaderCircle, Search, ShieldAlert } from "lucide-react";
import { useDemo } from "./demo-provider";
import FlowSteps from "./flow-steps";
import { Notice } from "./ui/notice";
import { useClipboard } from "./ui/clipboard";
import { findings, repairRequest, reportMarkdown, SAMPLE_REPO, SAMPLE_SITE } from "@/lib/sample";

type View = "scan" | "findings" | "repair" | "report" | "incident" | "help";
const titles: Record<Exclude<View, "scan">, [string, string, string]> = {
  findings: ["03 · SAMPLE RESULTS", "먼저, 이 순서로 살펴보세요.", "가상 서비스의 고정 예시입니다. 항목을 고르면 수정 안내로 이어집니다."],
  repair: ["04 · UNDERSTAND & REPAIR", "한 항목씩, 차근차근.", "근거를 이해하고 수정 요청을 준비하세요. 적용 후 확인할 항목도 함께 정리했어요."],
  report: ["SAMPLE REPORT", "점검 내용을 한눈에.", "샘플의 발견 항목과 현재 조치 표시를 문서로 가져가세요."],
  incident: ["OPTIONAL · INCIDENT NOTES", "확인한 사실부터, 차분하게.", "침해가 의심될 때 직접 확인한 사실을 기록하고 검토용 초안을 만드세요."],
  help: ["HELP & SCOPE", "시작하기 전에 알아두세요.", "체험의 사용 방법과 실제로 할 수 있는 일을 안내합니다."],
};

function SampleContext() {
  const { submitted } = useDemo();
  return <div className="sample-context"><span className="sample-label">고정 샘플 · 실제 검사 없음</span><code>{SAMPLE_SITE}</code><p>가상 서비스 · 예제 저장소 <code>{SAMPLE_REPO}</code></p>{submitted && <p>입력한 URL: <span>{submitted}</span><br/>이 주소에 접속하거나 분석하지 않았습니다. 아래 내용은 가상 서비스의 예시입니다.</p>}</div>;
}

function Counts() {
  const { marked } = useDemo();
  return <dl className="count-grid"><div><dt>샘플 발견 항목</dt><dd>{findings.length}<small>건</small></dd></div><div><dt>아직 미조치</dt><dd>{findings.length - marked.length}<small>건</small></dd></div><div><dt>재검증 대기</dt><dd className="accent">{marked.length}<small>건</small></dd></div><div><dt>검증 완료</dt><dd>0<small>건</small></dd></div></dl>;
}

function Simulation() {
  const { running, ready, submitted, phase, advanceSimulation, cancelSimulation } = useDemo();
  const router = useRouter();
  const startedHere = useRef(running);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(advanceSimulation, 1100);
    return () => clearInterval(timer);
  }, [running, advanceSimulation]);
  useEffect(() => {
    if (running) startedHere.current = true;
    if (ready && startedHere.current) { startedHere.current = false; router.replace("/findings"); }
  }, [running, ready, router]);
  if (!running) return <section className="card empty-state"><Globe2 size={32}/><h1>{ready ? "이 체험은 이미 마쳤어요." : "진행 중인 체험이 없어요."}</h1><p>새로고침하면 진행 상태가 초기화됩니다.<br/>URL을 다시 입력하거나 고정 샘플을 살펴보세요.</p><div className="center-actions"><Link className="button primary" href="/">URL 입력하기 <ArrowRight size={16}/></Link><Link className="button secondary" href="/findings">샘플 결과 보기</Link></div></section>;
  const phases = ["입력한 주소 형식 확인", "샘플 관찰 항목 불러오기", "예시의 우선순위 정리", "수정 안내 준비"];
  return <section className="card progress-card">
    <div className="progress-symbol"><LoaderCircle className="spin" size={29}/></div>
    <p className="eyebrow">02 · DEMO IN PROGRESS</p><h1>점검 흐름을 체험하고 있어요.</h1><p className="muted">샘플 준비가 끝나면 결과 화면으로 이동합니다.</p>
    <div className="progress-target"><span>입력한 URL · 분석 대상 아님</span><code>{submitted}</code></div>
    <div className="simulation-progress"><div className="split-row"><strong>샘플 체험 진행률</strong><span>{phase * 25}%</span></div><progress aria-label="샘플 체험 진행률" max={4} value={phase}/><ol aria-live="polite">{phases.map((label, index) => <li key={label} className={phase > index ? "complete" : phase === index ? "current" : ""}><span>{phase > index ? <Check size={13}/> : index + 1}</span>{label}{phase === index && <span className="sr-only">진행 중</span>}</li>)}</ol></div>
    <Notice compact>진행률은 체험용 시뮬레이션입니다. 입력한 사이트에 접속하거나 실제 검사를 수행하지 않습니다.</Notice>
    <button className="text-link" onClick={() => { cancelSimulation(); router.replace("/"); }}>체험 취소하고 URL로 돌아가기</button>
  </section>;
}

function Findings() {
  const d = useDemo();
  const visible = findings.filter(f => (d.priority === "전체" || f.priority === d.priority) && (d.status === "전체" || (d.status === "재검증 대기" ? d.marked.includes(f.id) : !d.marked.includes(f.id))) && `${f.id} ${f.title} ${f.location} ${f.category}`.toLowerCase().includes(d.search.toLowerCase().trim()));
  function reset() { d.setSearch(""); d.setPriority("전체"); d.setStatus("전체"); }
  return <>
    <SampleContext/><Counts/>
    <section className="result-intro card"><div><p className="eyebrow">NEXT STEP</p><h2>먼저 긴급 항목의 근거부터 확인하세요.</h2><p>위험도는 샘플의 검토 순서입니다. 내 서비스에 해당하는지는 실제 환경에서 확인해야 합니다.</p></div><Link className="button primary" href={`/repair/${findings[0].id}`}>첫 수정 안내 보기 <ArrowRight size={16}/></Link></section>
    <div className="results-toolbar"><div className="search-field"><Search size={17}/><label className="sr-only" htmlFor="finding-search">발견 항목 검색</label><input id="finding-search" type="search" value={d.search} onChange={e => d.setSearch(e.target.value)} placeholder="항목명, 위치, ID로 검색"/></div><div className="filter-field"><label htmlFor="priority">위험도</label><select id="priority" value={d.priority} onChange={e => d.setPriority(e.target.value)}>{["전체", "긴급", "높음", "보통"].map(v => <option key={v}>{v}</option>)}</select></div><div className="filter-field"><label htmlFor="finding-status">조치 상태</label><select id="finding-status" value={d.status} onChange={e => d.setStatus(e.target.value)}>{["전체", "미조치", "재검증 대기"].map(v => <option key={v}>{v}</option>)}</select></div></div>
    <p className="results-caption" role="status">{visible.length}개 항목 · 우선순위 높은 순</p>
    {visible.length === 0 ? <div className="card empty-state"><Search size={30}/><h2>조건에 맞는 항목이 없어요.</h2><p>검색어나 필터를 바꿔 보세요. 이 화면은 안전 판정이 아닙니다.</p><button className="button secondary" onClick={reset}>필터 초기화</button></div> : <ul className="findings-list" aria-label="발견 항목 목록">{visible.map((finding, index) => <li key={finding.id}><Link className="finding-row" href={`/repair/${finding.id}`}><span className="finding-number">{String(index + 1).padStart(2, "0")}</span><div className="finding-summary"><div className="finding-tags"><span className={`severity-badge severity-${finding.priority}`}>{finding.priority}</span><code>{finding.id}</code><span>{finding.category}</span></div><h2>{finding.title}</h2><p>{finding.location}</p></div><span className={`finding-status ${d.marked.includes(finding.id) ? "accent" : "muted"}`}>{d.marked.includes(finding.id) ? "재검증 대기" : "미조치"}</span><ChevronRight size={18}/></Link></li>)}</ul>}
    <div className="support-grid"><article className="card"><FileText size={21}/><h2>조치 현황을 문서로</h2><p>현재 표시와 수정 가이드를 Markdown으로 가져가세요.</p><Link className="text-link" href="/report">리포트 보기 <ArrowRight size={14}/></Link></article><article className="card"><ShieldAlert size={21}/><h2>침해가 의심되나요?</h2><p>직접 확인한 사실이 있다면 대응 초안을 기록할 수 있어요.</p><Link className="text-link" href="/incident">사고 사실 기록하기 <ArrowRight size={14}/></Link></article></div>
  </>;
}

function Repair({ findingId }: { findingId?: string }) {
  const d = useDemo();
  const clipboard = useClipboard();
  const selected = findings.find(f => f.id === findingId) ?? findings[0];
  const request = repairRequest(selected);
  const next = findings[findings.indexOf(selected) + 1];
  return <><SampleContext/><div className="repair-layout"><article className="card finding-detail" aria-label="선택한 발견 항목 상세"><div className="split-row"><span className="eyebrow">{selected.id} · SAMPLE EVIDENCE</span><span className={`severity-badge severity-${selected.priority}`}>{selected.priority}</span></div><h2>{selected.title}</h2><p>{selected.observation}</p>
    <div className="detail-section"><h3>왜 확인해야 하나요?</h3><p>{selected.impact}</p></div>
    <div className="detail-section"><h3>가상 서비스의 관찰 근거</h3><div className="code-block"><div><Code2 size={14}/><span>{selected.location}</span></div><pre><code>{selected.evidence}</code></pre></div></div>
    <div className="detail-section"><h3>이 순서로 검토하세요</h3><ol className="repair-steps">{selected.steps.map((step, index) => <li key={step}><span>{index + 1}</span><p>{step}</p></li>)}</ol></div>
    <div className="verification-note"><CheckCheck size={20}/><div><h3>수정 후 직접 확인할 것</h3><p>{selected.verify}</p></div></div>
    <div className="prompt-box"><div className="split-row"><h3>AI 코딩 도구에 전달하기</h3><span className="sample-label">고정 샘플</span></div><p>내 프로젝트에 해당하는지 확인한 뒤 사용하세요. 이 화면이 코드를 수정하지는 않습니다.</p><details><summary>수정 요청문 미리 보기</summary><pre>{request}</pre></details><button className="button primary" onClick={() => clipboard.copy(request)}><Clipboard size={16}/>AI 수정 요청 복사</button><p className="feedback" role="status">{clipboard.feedback}</p></div>
    <div className="pending-action"><div><h3>직접 조치했다면 표시하세요.</h3><p>실제 재검증은 지원하지 않으며, 표시해도 검증 완료가 되지 않습니다.</p></div><button className="button secondary" onClick={() => d.setMarked(ids => ids.includes(selected.id) ? ids.filter(id => id !== selected.id) : [...ids, selected.id])}>{d.marked.includes(selected.id) ? "조치 표시 취소" : "조치함 · 재검증 대기"}</button></div>
    <div className="repair-bottom-actions"><Link className="text-link" href="/findings"><ArrowLeft size={14}/>결과 목록</Link>{next ? <Link className="text-link" href={`/repair/${next.id}`}>다음 항목 보기 <ArrowRight size={14}/></Link> : <Link className="text-link" href="/report">리포트로 정리하기 <ArrowRight size={14}/></Link>}</div>
    </article><aside className="repair-aside"><section className="card"><h2>검토할 샘플 항목</h2><ul>{findings.map(f => <li key={f.id}><Link href={`/repair/${f.id}`} className={selected.id === f.id ? "selected" : ""} aria-current={selected.id === f.id ? "page" : undefined}><span className={`severity-badge severity-${f.priority}`}>{f.priority}</span><span>{f.title}</span>{d.marked.includes(f.id) && <Check size={14} aria-label="재검증 대기"/>}</Link></li>)}</ul></section><section className="card"><h2>현재 조치 표시</h2><p><strong className="accent">{d.marked.length}건</strong> 재검증 대기 · 검증 완료 0건</p><Link className="text-link" href="/report">리포트와 다운로드 <ArrowRight size={14}/></Link></section></aside></div></>;
}

function Report() {
  const d = useDemo();
  const clipboard = useClipboard();
  const [downloadStatus, setDownloadStatus] = useState("");
  const markdown = reportMarkdown(d.marked, d.submitted);
  function download() {
    clipboard.clearFeedback();
    try {
      const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "72hours-sample-report.md"; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000); setDownloadStatus("Markdown 파일 다운로드를 요청했습니다.");
    } catch { setDownloadStatus("다운로드를 시작하지 못했습니다. 리포트 복사를 이용해 주세요."); }
  }
  return <><SampleContext/><Counts/><div className="report-actions"><button className="button primary" onClick={download}><Download size={16}/>Markdown 다운로드</button><button className="button secondary" onClick={() => { setDownloadStatus(""); void clipboard.copy(markdown); }}><Clipboard size={15}/>리포트 복사</button><Link className="text-link" href="/findings">조치 현황 수정 <ArrowRight size={15}/></Link></div><p className="feedback" role="status">{clipboard.feedback || downloadStatus}</p><section className="card report-sheet"><div className="report-heading"><div><p className="eyebrow">72HOURS · SAMPLE REPORT</p><h2>보안 점검 요약</h2></div><FileText size={30} className="muted"/></div><Notice compact>모든 내용은 가상 서비스의 고정 예시입니다. 입력한 주소에 대한 검사나 보안 판정이 아닙니다.</Notice><div className="report-table-wrap"><table><caption className="sr-only">샘플 발견 항목과 조치 상태</caption><thead><tr><th>발견 항목</th><th>위험도</th><th>조치 상태</th></tr></thead><tbody>{findings.map(f => <tr key={f.id}><td><span className="caption muted">{f.id}</span><strong>{f.title}</strong><code>{f.location}</code></td><td><span className={`severity-badge severity-${f.priority}`}>{f.priority}</span></td><td><span className={d.marked.includes(f.id) ? "accent" : "muted"}>{d.marked.includes(f.id) ? "재검증 대기" : "미조치"}</span></td></tr>)}</tbody></table></div><div className="report-bottom"><h3>리포트를 읽는 방법</h3><p>긴급 항목부터 관찰 근거와 영향을 검토하세요. ‘재검증 대기’는 사용자가 조치를 표시한 항목이며 해결을 입증하지 않습니다. 검증 완료는 항상 0건입니다.</p><p>다운로드에는 관찰 내용과 영향, 수정 가이드, 직접 확인할 항목이 포함됩니다.</p></div></section></>;
}

function Incident() {
  const d = useDemo();
  const clipboard = useClipboard();
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState("");
  function generate(event: FormEvent) {
    event.preventDefault();
    if (!d.facts.service.trim() || !d.facts.date || !d.facts.observation.trim()) { setError("서비스명, 인지 시각, 확인한 사실을 모두 입력해 주세요."); return; }
    setError(""); clipboard.clearFeedback();
    d.setDraft(`[검토용 사고 대응 초안 — 전송되지 않음]\n\n서비스: ${d.facts.service.trim()}\n인지 시각: ${d.facts.date.replace("T", " ")} (사용자 입력, 시간대 별도 확인)\n\n1. 확인한 사실\n${d.facts.observation.trim()}\n\n2. 지금까지의 조치\n${d.facts.action.trim() || "아직 입력하지 않음"}\n\n3. 추가로 확인할 사항\n영향 범위, 발생 원인, 관련 데이터, 추가 대응과 신고 의무는 별도 확인이 필요합니다.\n\n이 초안은 입력한 사실만 정리한 문서입니다. 법률 자문 또는 공식 신고서가 아닙니다. 사실관계를 검토하고 필요한 경우 전문가 및 공식 기관에 문의하세요.`);
    setGenerated("입력한 사실로 초안을 만들었습니다. 편집 영역에서 검토해 주세요.");
  }
  const fields = [["service", "서비스명", "예: 내가 운영하는 서비스"], ["date", "문제를 인지한 시각", ""], ["observation", "확인한 사실", "직접 확인한 현상과 범위를 적어 주세요. 추측과 개인정보는 제외하세요."], ["action", "지금까지 취한 조치 (선택)", "실제로 진행한 조치만 적어 주세요."]] as const;
  return <><Notice>빈 양식에 직접 확인한 사실만 입력하세요. 입력 내용은 외부로 전송되지 않으며 새로고침하면 사라집니다.</Notice><div className="incident-layout"><section className="card form-card"><div className="panel-heading"><FileText size={22}/><h2>사실 기록</h2></div><form onSubmit={generate} noValidate>{fields.map(([key, label, placeholder]) => <div className="form-field" key={key}><label htmlFor={`incident-${key}`}>{label}{key !== "action" && <span className="accent" aria-label="필수"> *</span>}</label>{key === "observation" || key === "action" ? <textarea id={`incident-${key}`} rows={key === "observation" ? 5 : 3} placeholder={placeholder} value={d.facts[key]} onChange={e => d.setFacts({ ...d.facts, [key]: e.target.value })} required={key !== "action"}/> : <input id={`incident-${key}`} type={key === "date" ? "datetime-local" : "text"} placeholder={placeholder} value={d.facts[key]} onChange={e => d.setFacts({ ...d.facts, [key]: e.target.value })} required/>}</div>)}{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary" type="submit">{d.draft ? "입력한 사실로 초안 다시 만들기" : "검토용 초안 만들기"}<ArrowRight size={16}/></button>{d.draft && <p className="field-hint">다시 만들면 편집 중인 초안이 위 사실 기록으로 교체됩니다.</p>}</form></section><section className="card draft-card"><div className="panel-heading"><h2>대응 초안</h2><span className="sample-label">직접 편집 가능</span></div><p className="muted">작성 후 사실관계를 검토하세요. 신고를 제출하지 않습니다.</p><label className="sr-only" htmlFor="incident-draft">편집 가능한 대응 초안</label><textarea id="incident-draft" value={d.draft} onChange={e => { d.setDraft(e.target.value); setGenerated(""); clipboard.clearFeedback(); }} placeholder="확인한 사실을 입력하면 이곳에 초안이 만들어집니다." rows={19}/><button className="button secondary" disabled={!d.draft.trim()} onClick={() => clipboard.copy(d.draft)}><Clipboard size={15}/>초안 복사</button><p className="feedback" role="status">{clipboard.feedback || generated}</p><p className="fine-print">민감한 정보와 인증정보는 입력하지 마세요. 법적 판단이나 신고 의무는 전문가에게 확인하세요.</p></section></div></>;
}

function Help() {
  return <div className="help-layout"><section className="help-content"><article className="card"><CircleHelp size={24} className="accent"/><h2>URL 하나로 시작하고, 한 단계씩.</h2><ol className="repair-steps"><li><span>1</span><div><h3>웹사이트 URL 입력</h3><p>공개 도메인의 HTTP 또는 HTTPS 주소를 입력하세요. 도메인만 쓰면 HTTPS를 붙입니다. 로그인 정보, 쿼리와 해시가 있는 주소, 로컬 주소와 IP는 받지 않습니다.</p></div></li><li><span>2</span><div><h3>샘플 점검 체험</h3><p>전용 진행 화면에서 취소할 수 있고, 완료하면 결과로 자동 이동합니다. 실제 사이트에 접속하지 않는 시뮬레이션입니다.</p></div></li><li><span>3</span><div><h3>결과와 수정 안내</h3><p>고정된 가상 서비스의 항목을 검색·필터링하고 선택하세요. 관찰 근거, 수정 순서와 AI 코딩 도구에 전달할 예시 요청문을 확인할 수 있습니다.</p></div></li><li><span>4</span><div><h3>확인하고 문서로 정리</h3><p>직접 조치한 항목은 ‘재검증 대기’로 표시합니다. 결과 화면에서 리포트를 받거나, 필요한 경우 빈 사고 사실 기록을 작성하세요.</p></div></li></ol></article><article className="card"><h2>체험과 실제 검사의 범위</h2><p><Link className="text-link" href="/repository">GitHub 저장소 실제 검사로 이동 <ArrowRight size={14}/></Link></p><dl className="help-definitions"><div><dt>웹사이트 URL 샘플 체험</dt><dd>주소 형식만 확인하며 사이트에 접속하지 않습니다. 샘플의 내용은 입력한 주소의 진단이 아닙니다.</dd></div><div><dt>GitHub 저장소 실제 검사</dt><dd>별도 실제 검사 화면은 공개 저장소 주소를 기존 엔진 API로 보내고 결과를 조회합니다. 같은 저장소를 재검사하면 이전 결과와 비교합니다. 추가 AI 해석이 실패해도 엔진 결과는 남습니다. 마지막 결과와 조치 표시는 브라우저에 보관합니다. 서버 코드나 DB 정책을 웹사이트 URL만으로 분석하지 않습니다.</dd></div><div><dt>샘플의 출처</dt><dd>모든 관찰 내용은 {SAMPLE_SITE}, 예제 저장소 {SAMPLE_REPO}의 가상 예시입니다. 실제 입력한 URL의 문제를 입증하지 않습니다.</dd></div><div><dt>샘플 입력과 상태 유지</dt><dd>주소·조치 표시·초안은 현재 탭에서 화면을 이동하는 동안 유지됩니다. 새로고침하면 사라지고, 새 URL 체험을 시작하면 샘플 조치와 필터가 초기화됩니다. 테마만 브라우저에 저장합니다.</dd></div><div><dt>수정 요청과 문서</dt><dd>복사는 실제 브라우저 권한에 따라 성공/실패를 안내합니다. 코드를 수정하거나 사고를 신고하지 않으며, 검토용 안내와 문서를 제공합니다.</dd></div></dl></article></section><aside className="card help-aside"><ShieldAlert size={25} className="accent"/><h3>조치 표시와 검증은 달라요.</h3><p className="muted">실제 코드와 배포 환경에서 체크리스트를 확인해야 합니다. 샘플의 검증 완료는 항상 0건이며, 실제 저장소 화면은 엔진이 반환한 코드 해결 상태만 집계합니다.</p><Link className="button primary" href="/">URL로 시작하기 <ArrowRight size={16}/></Link><Link className="text-link" href="/incident">사고 사실 기록하기 <ArrowRight size={15}/></Link></aside></div>;
}

export default function Workspace({ view, findingId }: { view: View; findingId?: string }) {
  if (view === "scan") return <main id="main" className="workspace progress-page container" tabIndex={-1}><FlowSteps step={2}/><Simulation/></main>;
  const [eyebrow, title, description] = titles[view];
  const backToResults = ["repair", "report", "incident"].includes(view);
  return <main id="main" className="workspace container" tabIndex={-1}>
    {(view === "findings" || view === "repair") && <FlowSteps step={view === "findings" ? 3 : 4}/>}
    <Link className="back-link" href={backToResults ? "/findings" : "/"}><ArrowLeft size={14}/>{backToResults ? "결과 목록으로" : "URL 입력으로"}</Link>
    <div className="workspace-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
    {view === "findings" ? <Findings/> : view === "repair" ? <Repair findingId={findingId}/> : view === "report" ? <Report/> : view === "incident" ? <Incident/> : <Help/>}
  </main>;
}
