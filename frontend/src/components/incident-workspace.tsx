"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, Check, Clipboard, Clock, Download, ExternalLink, FileText, GitBranch, LoaderCircle, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import { useIncident, type IncidentEvidence } from "./incident-provider";
import { useRepository } from "./repository-provider";
import { Notice } from "./ui/notice";
import { useClipboard } from "./ui/clipboard";
import { autoSuggestions, draftBlockers, getAssessmentGaps, incidentTypeLabels, koreaNow, mergeActions, remainingQuestions, scanActions, scanCheckLine, urgentEvidence, type RemainingQuestion } from "@/lib/incident";
import type { Deadline, FilingKind, IncidentForm, IncidentType } from "@/types/incident";

const kinds: FilingKind[] = ["incident_24h", "privacy_72h"];
const filingNames: Record<FilingKind, string> = { incident_24h: "침해사고 신고서", privacy_72h: "개인정보 유출 신고서·통지문" };
const shortNames: Record<FilingKind, string> = { incident_24h: "24h", privacy_72h: "72h" };
const official = {
  incident: "https://www.boho.or.kr/kr/subPage.do?menuNo=205033",
  privacy: "https://www.privacy.go.kr/front/wcp/spl/splRptInfo.do",
  law: "https://law.go.kr/lsLinkCommonInfo.do?lspttninfSeq=67073",
};
const reviewNotice = "검토용 초안 · 기관에 접수되지 않았습니다. 정보주체 통지(유출 가능성 통지 포함) 의무는 자동 판정하지 않으니 별도로 확인하세요. 제출 전 최신 법령과 공식 서식을 대조하고 사실관계를 검토하세요.";

type TextKey = { [K in keyof IncidentForm]: IncidentForm[K] extends string ? K : never }[keyof IncidentForm];
type ChoiceKey = "incidentStatus" | "filingType" | "leakState" | "includesSensitive" | "includesUniqueId" | "externalAccess" | "recoveredLowRisk" | "subjectsNotified";
type Option = readonly [string, string];
const tri: readonly Option[] = [["yes", "예"], ["no", "아니요"], ["unknown", "아직 모름"]];
const choices: Record<ChoiceKey, { legend: string; options: readonly Option[]; hint?: string }> = {
  incidentStatus: { legend: "지금 상태는요?", options: [["ongoing", "대응 중"], ["contained", "확산 차단"], ["recovered", "복구 완료"], ["unknown", "아직 모름"]] },
  filingType: { legend: "이 사고로 이미 신고했나요?", options: [["initial", "처음 신고"], ["supplement", "이미 신고 · 보완"], ["unknown", "아직 모름"]] },
  leakState: { legend: "개인정보가 빠져나갔나요?", options: [["confirmed", "유출 확인"], ["suspected", "유출 의심"], ["none", "정황 없음"], ["unknown", "아직 모름"]],
    hint: "기관 신고와 영향받은 분들께 알리는 통지는 따로 확인합니다." },
  includesSensitive: { legend: "민감정보(건강·정치적 견해 등)가 포함됐나요?", options: tri },
  includesUniqueId: { legend: "고유식별정보(주민등록번호·여권번호 등)가 포함됐나요?", options: tri },
  externalAccess: { legend: "외부의 불법 접근으로 빠져나갔나요?", options: tri },
  recoveredLowRisk: { legend: "유출 정보를 회수·삭제해 피해 가능성이 현저히 낮아졌나요?", options: tri, hint: "취약점을 고친 것과는 다릅니다. 확인한 경우에만 ‘예’를 고르세요." },
  subjectsNotified: { legend: "영향받은 분들께 이미 알렸나요?", options: tri },
};
const privacyChoices: ChoiceKey[] = ["includesSensitive", "includesUniqueId", "externalAccess", "recoveredLowRisk", "subjectsNotified"];
const hasPersonalInfo = (form: IncidentForm) => form.leakState === "suspected" || form.leakState === "confirmed";

function OfficialLink({ href, children }: { href: string; children: ReactNode }) {
  return <a className="text-link" href={href} target="_blank" rel="noreferrer">{children}<ExternalLink size={13}/></a>;
}
function Spinner() { return <LoaderCircle className="spin" size={16}/>; }
function useAnyBusy() { const { busy } = useIncident(); return busy.assessment || busy.incident_24h || busy.privacy_72h; }

function Field({ name, label, type = "text", multiline = false, hint, maxLength, required = false }: {
  name: TextKey; label: string; type?: string; multiline?: boolean; hint?: string; maxLength?: number; required?: boolean;
}) {
  const { form, updateForm } = useIncident();
  const id = `incident-${name}`;
  const props = { id, name, value: form[name], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => updateForm(name, event.target.value),
    "aria-describedby": hint ? `${id}-hint` : undefined, maxLength, required };
  return <div className="form-field"><label htmlFor={id}>{label}{required && <span className="accent"> *</span>}</label>
    {multiline ? <textarea {...props} rows={4}/> : <input {...props} type={type}/>}
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>;
}

function Choice({ name }: { name: ChoiceKey }) {
  const { form, updateForm } = useIncident();
  const { legend, options, hint } = choices[name];
  return <fieldset className="incident-question" aria-describedby={hint ? `incident-${name}-hint` : undefined}><legend>{legend}</legend>
    <div className="incident-chips">{options.map(([value, label]) => <label className="incident-chip" key={value}>
      <input type="radio" name={`incident-${name}`} value={value} checked={form[name] === value} onChange={() => updateForm(name, value as IncidentForm[typeof name])}/><span>{label}</span>
    </label>)}</div>
    {hint && <p className="field-hint" id={`incident-${name}-hint`}>{hint}</p>}
  </fieldset>;
}

function IncidentTypes() {
  const { form, updateForm } = useIncident();
  return <fieldset className="incident-question"><legend>어떤 상황인가요? <span className="muted">여러 개 · 모르면 비워 두세요</span></legend>
    <div className="incident-chips">{(Object.entries(incidentTypeLabels) as [IncidentType, string][]).map(([kind, label]) => <label className="incident-chip" key={kind}>
      <input type="checkbox" checked={form.incidentTypes.includes(kind)} onChange={event => updateForm("incidentTypes", event.target.checked
        ? [...form.incidentTypes, kind] : form.incidentTypes.filter(value => value !== kind))}/><span>{label}</span>
    </label>)}</div>
  </fieldset>;
}

function PrivacyFacts() {
  const d = useIncident();
  return <div className="incident-conditional"><h3>개인정보 신고 판단에 필요한 사실</h3>
    <div className="incident-fields"><Field name="affectedCount" label="영향받은 인원" type="number" hint="모르면 비워 두세요. 빈칸은 0명이 아닙니다."/><Field name="personalItems" label="유출된 항목" hint="이메일, 이름처럼 항목명만 쉼표로 구분하세요."/></div>
    <label className="incident-choice"><input type="checkbox" checked={d.form.countIsEstimate} onChange={event => d.updateForm("countIsEstimate", event.target.checked)}/><span>인원은 추정치예요</span></label>
    {privacyChoices.map(name => <Choice key={name} name={name}/>)}
    {d.form.subjectsNotified === "yes" && <div className="incident-fields"><Field name="notifiedAt" label="알린 시각 · 한국 시간" type="datetime-local"/><Field name="notifyMethod" label="알린 방법" maxLength={200}/></div>}
  </div>;
}

function Evidence() {
  const incident = useIncident();
  const repository = useRepository();
  const candidates: IncidentEvidence[] = (repository.reportInput?.findings ?? []).flatMap(value => {
    if (!value || typeof value !== "object" || !("fingerprint" in value) || typeof value.fingerprint !== "string") return [];
    const finding = value as Record<string, unknown>;
    return [{ repo: repository.resultRepo, fingerprint: String(finding.fingerprint), title: String(finding.title || finding.fingerprint), finding: value }];
  });
  if (!candidates.length) return null;
  const urgent = urgentEvidence(candidates).filter(item => !incident.evidence.some(value => value.repo === item.repo && value.fingerprint === item.fingerprint));
  return <details className="incident-disclosure" open><summary>원인 후보로 연결할 발견 <span className="muted">선택 · {incident.evidence.length}/50</span></summary>
    <p className="field-hint">고른 발견은 초안의 원인 칸에 ‘자동 제안 · 확인 필요’로만 들어갑니다. 공격 시도나 취약점이 곧 침해 사실은 아닙니다.</p>
    {urgent.length > 0 && <button type="button" className="button secondary" disabled={incident.evidence.length + urgent.length > 50}
      onClick={() => urgent.forEach(item => incident.toggleEvidence(item))}>위험도 높은 발견 {urgent.length}건 한 번에 고르기</button>}
    <div className="incident-evidence-list">{candidates.map(item => {
      const selected = incident.evidence.some(value => value.repo === item.repo && value.fingerprint === item.fingerprint);
      return <label className="incident-choice" key={item.fingerprint}><input type="checkbox" checked={selected} disabled={!selected && incident.evidence.length >= 50} onChange={() => incident.toggleEvidence(item)}/><span>{item.title}<small>검사 발견 · 침해 사실 미확정</small></span></label>;
    })}</div>
  </details>;
}

function ScanImport() {
  const d = useIncident();
  const repository = useRepository();
  if (!repository.reportInput || !repository.resultRepo)
    return <p className="incident-scan-empty muted">검사 없이 시작해도 됩니다. 저장소를 검사했다면 수정·재검사 기록을 조치 내용으로 가져올 수 있습니다.</p>;
  // 점검을 실행한 사실을 첫 줄로, 그 뒤에 수정·재검사 기록을 붙입니다
  const actions = [scanCheckLine(repository.resultRepo, repository.findings), ...scanActions(repository.findings, repository.pendingIds)];
  const current = d.form.actions.split(/\r?\n/).map(line => line.trim());
  const fresh = actions.filter(line => !current.includes(line));
  return <section className="incident-scan" aria-labelledby="incident-scan-title">
    <div className="incident-scan-heading"><GitBranch size={18}/><div><h3 id="incident-scan-title">검사 기록에서 가져오기</h3><code>{repository.resultRepo}</code></div></div>
    {actions.length ? <>
      <ul className="incident-bullets">{actions.slice(0, 4).map(line => <li key={line}>{line}</li>)}{actions.length > 4 && <li>외 {actions.length - 4}건</li>}</ul>
      <button type="button" className="button secondary" disabled={!fresh.length} onClick={() => d.applyFacts({ actions: mergeActions(d.form.actions, fresh) })}>
        {fresh.length ? <>조치 기록에 {fresh.length}건 추가</> : <><Check size={15}/>조치 기록에 추가함</>}</button>
    </> : <p className="field-hint">아직 수정·재검사 기록이 없습니다. 수정 후 재검사하거나 조치 표시를 하면 여기에서 가져올 수 있습니다.</p>}
    <Evidence/>
  </section>;
}

function Facts() {
  const d = useIncident();
  const busy = useAnyBusy();
  const blockers = draftBlockers(d.form);
  return <section className="card incident-panel" aria-labelledby="incident-facts-title">
    <div className="incident-panel-intro"><p className="eyebrow">01 · CONFIRMED FACTS</p><h2 id="incident-facts-title">신고 판단에 필요한 것만 먼저 묻습니다.</h2>
      <p className="muted">회사 정보·원인·피해처럼 문서에 들어갈 나머지 칸은 초안을 만든 뒤, 서버가 비어 있다고 알려 준 칸만 골라 묻습니다. 모르는 항목은 ‘아직 모름’으로 두세요.</p></div>
    <ScanImport/>
    <form onSubmit={event => { event.preventDefault(); void d.prepare(); }} noValidate>
      <div className="form-field"><label htmlFor="incident-discoveredAt">문제를 알게 된 시각 · 한국 시간<span className="accent"> *</span></label>
        <div className="incident-inline"><input id="incident-discoveredAt" type="datetime-local" value={d.form.discoveredAt} required aria-describedby="incident-discoveredAt-hint"
          onChange={event => d.updateForm("discoveredAt", event.target.value)}/>
          <button type="button" className="button secondary" onClick={() => d.updateForm("discoveredAt", koreaNow())}><Clock size={15}/>지금</button></div>
        <p className="field-hint" id="incident-discoveredAt-hint">24·72시간 신고 기한이 이 시각부터 계산됩니다. 검사 실행 시각이 아니라 사고를 알게 된 시각입니다.</p></div>
      <Field name="summary" label="무슨 일이 있었나요?" multiline maxLength={1000} hint="직접 확인한 현상과 근거만 적어 주세요. 원시 로그, 비밀키, 개인별 정보는 넣지 마세요."/>
      <IncidentTypes/>
      <Choice name="incidentStatus"/>
      <Choice name="filingType"/>
      <Choice name="leakState"/>
      {hasPersonalInfo(d.form) && <PrivacyFacts/>}
      <Field name="actions" label="지금까지 한 조치" multiline hint="실제로 한 조치를 한 줄에 하나씩 적어 주세요."/>
      <ul className="incident-plan" aria-label="이 사실로 만들 문서">{kinds.map(kind => <li key={kind} className={blockers[kind].length ? "is-blocked" : ""}>
        {blockers[kind].length ? <span>{filingNames[kind]} · 필요: {blockers[kind].join(", ")}</span> : <><Check size={14}/><span>{filingNames[kind]} 초안을 함께 만듭니다</span></>}
      </li>)}</ul>
      {d.errors.assessment && <p className="form-error" role="alert">{d.errors.assessment}</p>}
      <div className="incident-actions"><button className="button primary" type="submit" disabled={busy}>{busy ? <Spinner/> : <Sparkles size={16}/>}신고 대상 확인하고 초안 만들기</button></div>
      <p className="fine-print">버튼을 누르면 입력한 사고 정보를 문서 생성 서버로 보냅니다. 공식 기관에 신고하거나 통지하지 않습니다. 입력은 화면 이동 동안 유지되며 새로고침하면 사라집니다.</p>
    </form>
  </section>;
}

function DeadlineView({ deadline }: { deadline: Deadline }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  const remaining = deadline.stopped_at ? deadline.remaining_minutes : Math.floor((new Date(deadline.due_at).getTime() - now) / 60_000);
  const overdue = deadline.overdue || remaining < 0;
  const time = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(deadline.due_at));
  return <div className={`incident-deadline ${overdue ? "is-overdue" : ""}`}><strong>{overdue ? "기한 경과 · 즉시 확인" : `${Math.floor(remaining / 60)}시간 ${remaining % 60}분 남음`}</strong><span>마감 {time} · 한국 시간</span><small>{deadline.basis}</small></div>;
}

function Duties({ stale }: { stale: boolean }) {
  const d = useIncident();
  return <div className="incident-duty-list">
    {d.assessment?.result.needs.map(need => {
      const gaps = getAssessmentGaps(d.form, need.kind);
      const incomplete = !need.required && gaps.length > 0;
      return <article className="card incident-duty" key={need.kind}>
        <div className="incident-duty-heading"><span className="incident-hour">{shortNames[need.kind]}</span><div><p className="eyebrow">{need.kind === "incident_24h" ? "KISA · 침해사고" : "개인정보보호위원회 · 유출 신고"}</p><h3>{need.kind === "incident_24h" ? "침해사고 신고" : "개인정보 유출 신고"}</h3></div></div>
        <span className={`incident-status ${need.required && !stale ? "needs-action" : ""}`}>{stale ? "입력 변경 · 다시 확인" : need.required ? "신고 대상 안내 · 적용 범위 확인" : incomplete ? "판단 보류 · 남은 질문 확인" : "입력 기준 신고 요건 미확인"}</span>
        {!stale && <><ul className="incident-bullets">{(incomplete ? gaps : need.reasons).map(reason => <li key={reason}>{reason}</li>)}</ul>
          {need.deadline && <DeadlineView key={`${need.kind}:${need.deadline.due_at}:${d.assessment?.revision}`} deadline={need.deadline}/>}</>}
        <p className="fine-print">{need.kind === "incident_24h" ? "정보통신서비스 제공자 등 법정 적용 대상인지 공식 안내에서 함께 확인하세요." : "기관 신고의 안내입니다. 정보주체 통지 여부는 별도로 확인하세요."}</p>
      </article>;
    })}
    <article className="card incident-duty incident-notification"><div className="panel-heading"><ShieldAlert size={21}/><h3>정보주체 통지</h3></div><span className="incident-status">공식 기준 확인 필요</span>
      <p>기관에 신고하는 일과 영향을 받은 분들께 알리는 일은 별도입니다. 실제 유출 통지와 유출 가능성 통지는 적용 조건과 기산점이 다릅니다.</p>
      <p className="muted">현재 도우미는 통지 의무를 자동 판정하지 않습니다. 생성되는 통지문도 사실관계와 최신 요건을 확인해야 하는 검토용 초안입니다.</p>
      <OfficialLink href={official.law}>현행 통지·신고 기준 확인</OfficialLink></article>
  </div>;
}

// Unanswered choices when this assessment was made. Kept as a snapshot so a question does not vanish mid-answer.
function openChoices(form: IncidentForm): (ChoiceKey | "incidentTypes")[] {
  const open: (ChoiceKey | "incidentTypes")[] = [];
  if (form.incidentStatus === "unknown") open.push("incidentStatus");
  if (form.filingType === "unknown") open.push("filingType");
  if (!form.incidentTypes.length) open.push("incidentTypes");
  if (form.leakState === "unknown") open.push("leakState");
  if (hasPersonalInfo(form)) open.push(...privacyChoices.filter(name => form[name] === "unknown"));
  return open;
}

function QuestionInput({ question }: { question: RemainingQuestion }) {
  const tag = <span className="incident-provenance">{question.kinds.map(kind => shortNames[kind]).join(" · ")}</span>;
  return <div className="incident-question-field">{tag}
    <Field name={question.key} label={question.label} type={question.type === "textarea" ? "text" : question.type} multiline={question.type === "textarea"} hint={question.hint}/>
  </div>;
}

function Questions({ stale }: { stale: boolean }) {
  const d = useIncident();
  const busy = useAnyBusy();
  const [asked] = useState(() => openChoices(d.form));
  const [causeOpen, setCauseOpen] = useState(false);
  const reports = { incident_24h: d.documents.incident_24h?.report, privacy_72h: d.documents.privacy_72h?.report };
  const { questions, unmapped } = remainingQuestions({ incident_24h: reports.incident_24h?.missing, privacy_72h: reports.privacy_72h?.missing });
  const suggestions = autoSuggestions(reports);
  const showCause = causeOpen && !questions.some(question => question.key === "cause");
  const total = asked.length + questions.length;
  return <section className="card incident-panel incident-questions" aria-labelledby="incident-questions-title">
    <div className="incident-duty-heading"><span className="incident-hour">{total}</span><div><p className="eyebrow">SHARED QUESTIONS</p><h3 id="incident-questions-title">남은 질문</h3></div></div>
    <p className="muted">신고 판단에 필요한 사실과, 서버가 초안에서 비어 있다고 알려 준 칸입니다. 한 번 답하면 두 초안에 함께 반영됩니다. 모르는 칸은 비워 두고 먼저 신고한 뒤 보완할 수 있습니다.</p>
    {asked.map(name => name === "incidentTypes" ? <IncidentTypes key={name}/> : <Choice key={name} name={name}/>)}
    {questions.map(question => <QuestionInput key={question.key} question={question}/>)}
    {showCause && <Field name="cause" label="확인한 원인" multiline maxLength={2000} hint="자동 제안을 옮겼습니다. 확인한 내용만 남기고 추측은 ‘추정’이라고 표시하세요."/>}
    {!!unmapped.length && <p className="field-hint">초안에서 직접 보완할 칸: {unmapped.join(", ")}</p>}
    {!total && <p>남은 질문이 없습니다. 사실관계·신고 대상·최신 서식과 통지 의무는 제출 전에 따로 확인하세요.</p>}
    {!!suggestions.length && <div className="incident-suggestions"><h4><Sparkles size={15}/>서버가 자동으로 채운 칸 · 확인 필요</h4><dl>{suggestions.map(item => <div key={`${item.label}:${item.value}`}>
      <dt>{item.label}<span className="incident-provenance">{item.kinds.map(kind => shortNames[kind]).join(" · ")}</span></dt><dd>{item.value}</dd>
      {item.usableAs === "cause" && !showCause && <button type="button" className="text-link" onClick={() => { if (!d.form.cause.trim()) d.updateForm("cause", item.value); setCauseOpen(true); }}>원인 칸으로 옮겨 고쳐 쓰기</button>}
    </div>)}</dl></div>}
    <div className="incident-actions"><button className="button primary" disabled={!stale || busy} onClick={() => void d.prepare()}>{busy ? <Spinner/> : <RefreshCw size={16}/>}답변 반영해 다시 만들기</button>
      {!stale && !busy && <span className="field-hint">답을 바꾸면 다시 만들 수 있습니다.</span>}</div>
    {d.errors.assessment && <p className="form-error" role="alert">{d.errors.assessment}</p>}
  </section>;
}

function DocumentEditor({ kind }: { kind: FilingKind }) {
  const d = useIncident();
  const doc = d.documents[kind];
  const stale = !!doc && doc.revision !== d.revision;
  const blockers = draftBlockers(d.form)[kind];
  const [replace, setReplace] = useState(false);
  const [feedback, setFeedback] = useState("");
  const clipboard = useClipboard();
  const output = doc ? `> ${reviewNotice}\n> 공식 안내: ${official.incident}\n> 개인정보 신고: ${official.privacy}\n> 통지·신고 기준: ${official.law}\n\n${doc.markdown}` : "";
  function generate() {
    clipboard.clearFeedback(); setFeedback("");
    if (doc?.edited) setReplace(true);
    else void d.generate(kind);
  }
  function download() {
    const url = URL.createObjectURL(new Blob([output], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `72hours-${kind}-draft.md`;
    try { document.body.appendChild(anchor); anchor.click(); setFeedback("편집한 초안의 다운로드를 요청했습니다. 공식 기관에 접수되지 않았습니다."); }
    finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  }
  const status = doc ? (stale ? "입력 변경 · 갱신 필요" : doc.edited ? "직접 편집한 초안" : doc.report.status.text) : blockers.length ? "사실 확인 후 생성" : "초안 없음";
  return <article className="card incident-document" aria-labelledby={`${kind}-title`}>
    <div className="incident-duty-heading"><FileText size={22}/><div><p className="eyebrow">{kind === "incident_24h" ? "24 HOURS · KISA" : "72 HOURS · PRIVACY"}</p><h3 id={`${kind}-title`}>{filingNames[kind]}</h3></div></div>
    <span className={`incident-status ${doc && !stale && !doc.edited && doc.report.missing.length ? "needs-action" : ""}`}>{status}</span>
    {!doc && (kind === "privacy_72h" && d.form.leakState === "none"
      ? <p className="muted incident-document-note">개인정보 유출 정황이 없다고 기록했습니다. 유출이 의심되면 사실 기록을 바꾸세요.</p>
      : blockers.length ? <p className="muted incident-document-note">이 초안을 만들려면 확인해 주세요: {blockers.join(", ")}. 위 남은 질문에서 답할 수 있습니다.</p> : null)}
    {kind === "privacy_72h" && hasPersonalInfo(d.form) && d.form.leakState !== "confirmed" && <p className="incident-document-warning">유출 사실이 확정되지 않았습니다. 생성된 통지문이 유출을 확정한 표현을 포함하는지 확인하고, 의심 내용을 사실로 제출하지 마세요.</p>}
    {(!doc || stale || doc.edited) && !blockers.length && <div className="incident-actions"><button className="button secondary" disabled={d.busy[kind]} onClick={generate}>{d.busy[kind] ? <Spinner/> : <FileText size={16}/>}{doc ? "현재 사실로 다시 만들기" : "검토용 초안 만들기"}</button></div>}
    {replace && <div className="incident-replace" role="alert"><p>다시 만들면 이 문서에서 직접 편집한 내용이 현재 사실 기록으로 교체됩니다. 다른 신고서의 편집 내용은 유지됩니다.</p><button className="button secondary" onClick={() => setReplace(false)}>편집 내용 유지</button><button className="button primary" onClick={() => { setReplace(false); void d.generate(kind, true); }}>현재 사실로 교체</button></div>}
    {d.errors[kind] && <p className="form-error" role="alert">{d.errors[kind]}</p>}
    {doc && <>
      {stale && <Notice compact>공통 사실이 바뀌었습니다. 편집 내용은 보존했습니다. 다시 만든 뒤 복사·다운로드하세요.</Notice>}
      <div className="form-field incident-editor"><label htmlFor={`draft-${kind}`}>편집 가능한 Markdown 초안</label><textarea id={`draft-${kind}`} rows={14} value={doc.markdown} onChange={event => { d.editDocument(kind, event.target.value); clipboard.clearFeedback(); setFeedback(""); }} aria-describedby={`draft-${kind}-hint`}/><p className="field-hint" id={`draft-${kind}-hint`}>‘(제안값, 확인 필요)’ 표시는 서버가 대신 채운 값입니다. 직접 편집한 내용은 복사·다운로드에 반영되며, 남은 질문 목록은 다시 만들 때 갱신됩니다.</p></div>
      <p className="incident-document-warning">{reviewNotice}</p>
      <div className="incident-actions"><button className="button secondary" disabled={stale || !doc.markdown.trim()} onClick={() => { setFeedback(""); void clipboard.copy(output); }}><Clipboard size={15}/>편집한 초안 복사</button><button className="button secondary" disabled={stale || !doc.markdown.trim()} onClick={download}><Download size={15}/>Markdown 다운로드</button></div>
      <p className="feedback" role="status">{clipboard.feedback || feedback}</p>
      <div className="incident-destination"><h4>공식 제출처</h4><ul className="incident-bullets">{doc.report.submit_to.map(line => <li key={line}>{line}</li>)}</ul><OfficialLink href={kind === "incident_24h" ? official.incident : official.privacy}>공식 신고 안내 열기</OfficialLink>{doc.report.disclaimer && <p className="fine-print">{doc.report.disclaimer}</p>}</div>
    </>}
  </article>;
}

function Prepare() {
  const d = useIncident();
  const stale = d.assessment?.revision !== d.revision;
  return <section aria-labelledby="incident-prepare-title">
    <div className="incident-panel-intro"><p className="eyebrow">02 · PREPARE TO FILE</p><h2 id="incident-prepare-title">남은 것만 채우면 됩니다.</h2>
      <p className="muted">같은 사고 기록으로 두 신고의 대상·기한을 확인하고 초안을 만들었습니다. 문서를 만들어도 기관 접수나 정보주체 통지는 이루어지지 않습니다.</p></div>
    {stale && <Notice compact>사실 기록이 바뀌었습니다. 아래 안내와 초안은 이전 기록 기준입니다. ‘답변 반영해 다시 만들기’로 갱신하세요.</Notice>}
    <Duties stale={stale}/>
    <Questions key={d.assessment?.revision ?? 0} stale={stale}/>
    <div className="incident-documents">{kinds.map(kind => <DocumentEditor key={kind} kind={kind}/>)}</div>
    <div className="incident-actions"><button className="button secondary" onClick={() => d.setStep(0)}><ArrowLeft size={16}/>사실 기록 고치기</button></div>
  </section>;
}

export default function IncidentWorkspace() {
  const d = useIncident();
  const heading = useRef<HTMLDivElement>(null);
  const step = d.step > 0 ? 1 : 0;
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: "start" }); }, [step]);
  const labels = ["사실 확인", "신고 준비"];
  return <div className="incident-workspace">
    <nav className="incident-steps" aria-label="사고 신고 지원 단계"><ol>{labels.map((label, index) => <li key={label}><button aria-current={step === index ? "step" : undefined} disabled={index > 0 && !d.assessment} onClick={() => d.setStep(index)}><span>{step > index ? <Check size={14}/> : `0${index + 1}`}</span><strong>{label}</strong></button></li>)}</ol></nav>
    <div ref={heading} tabIndex={-1} className="incident-step-content" aria-label={labels[step]}>{step === 0 ? <Facts/> : <Prepare/>}</div>
  </div>;
}
