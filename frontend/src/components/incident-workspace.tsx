"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, ChevronRight, Clipboard, Download, ExternalLink, FileText, LoaderCircle, ShieldAlert } from "lucide-react";
import { useIncident, type IncidentEvidence } from "./incident-provider";
import { useRepository } from "./repository-provider";
import { Notice } from "./ui/notice";
import { useClipboard } from "./ui/clipboard";
import { getFilingDocument } from "@/lib/api";
import { getAssessmentGaps, incidentTypeLabels } from "@/lib/incident";
import type { Deadline, FilingKind, IncidentForm, IncidentType, ReportField, ReportSection } from "@/types/incident";

const filingNames: Record<FilingKind, string> = { incident_24h: "침해사고 신고서", privacy_72h: "개인정보 유출 신고서·통지문" };
const official = {
  incident: "https://www.boho.or.kr/kr/subPage.do?menuNo=205033",
  privacy: "https://www.privacy.go.kr/front/wcp/spl/splRptInfo.do",
  law: "https://law.go.kr/lsLinkCommonInfo.do?lspttninfSeq=67073",
};
const reviewNotice = "검토용 초안 · 기관에 접수되지 않았습니다. 통지 의무는 별도 확인이 필요하며, 생성 문서의 과태료·통지 안내에는 최신 개정 내용이 반영되지 않은 부분이 있습니다. 제출 전 최신 법령과 공식 서식을 대조하고 사실관계를 검토하세요.";

function OfficialLink({ href, children }: { href: string; children: ReactNode }) {
  return <a className="text-link" href={href} target="_blank" rel="noreferrer">{children}<ExternalLink size={13}/></a>;
}

type TextKey = { [K in keyof IncidentForm]: IncidentForm[K] extends string ? K : never }[keyof IncidentForm];
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

function Answer({ name, label, hint }: { name: "includesSensitive" | "includesUniqueId" | "externalAccess" | "recoveredLowRisk" | "subjectsNotified"; label: string; hint?: string }) {
  const { form, updateForm } = useIncident();
  return <div className="form-field"><label htmlFor={`incident-${name}`}>{label}</label>
    <select id={`incident-${name}`} value={form[name]} onChange={event => updateForm(name, event.target.value as IncidentForm[typeof name])} aria-describedby={hint ? `${name}-hint` : undefined}>
      <option value="unknown">아직 확인하지 못했어요</option><option value="yes">예</option><option value="no">아니요</option>
    </select>{hint && <p className="field-hint" id={`${name}-hint`}>{hint}</p>}
  </div>;
}

function Evidence() {
  const incident = useIncident();
  const repository = useRepository();
  const rawFindings = repository.reportInput?.findings ?? [];
  const candidates: IncidentEvidence[] = rawFindings.flatMap(value => {
    if (!value || typeof value !== "object" || !("fingerprint" in value) || typeof value.fingerprint !== "string") return [];
    const finding = value as Record<string, unknown>;
    return [{ repo: repository.resultRepo, fingerprint: String(finding.fingerprint), title: String(finding.title || finding.fingerprint), finding: value }];
  });
  return <details className="incident-disclosure"><summary>실제 검사 발견 연결 <span className="muted">선택 · {incident.evidence.length}/50</span></summary>
    <p className="field-hint">검사 발견은 기술적 근거 후보입니다. 실제 침해나 유출을 확인한 사실로 자동 반영하지 않습니다.</p>
    {candidates.length ? <><p className="incident-source">검사 대상 <code>{repository.resultRepo}</code></p><div className="incident-evidence-list">{candidates.map(item => {
      const selected = incident.evidence.some(value => value.repo === item.repo && value.fingerprint === item.fingerprint);
      return <label className="incident-choice" key={item.fingerprint}><input type="checkbox" checked={selected} disabled={!selected && incident.evidence.length >= 50} onChange={() => incident.toggleEvidence(item)}/><span>{item.title}<small>검사 발견 · 침해 사실 미확정</small></span></label>;
    })}</div></> : <p className="muted">연결할 검사 결과가 없습니다. 검사 없이도 사고 기록과 신고서 작성을 계속할 수 있습니다.</p>}
    {!!incident.evidence.length && <div className="incident-selected"><h3>이 사고에 연결한 항목</h3>{incident.evidence.map(item => <div key={`${item.repo}:${item.fingerprint}`}><span>{item.title}<small>{item.repo}</small></span><button type="button" className="text-link" onClick={() => incident.toggleEvidence(item)} aria-label={`${item.title} 연결 해제`}>해제</button></div>)}</div>}
  </details>;
}

function Facts() {
  const d = useIncident();
  const hasPersonalInfo = d.form.leakState === "suspected" || d.form.leakState === "confirmed";
  return <section className="card incident-panel" aria-labelledby="incident-facts-title">
    <div className="incident-panel-intro"><p className="eyebrow">01 · SHARED FACTS</p><h2 id="incident-facts-title">무슨 일이 있었나요?</h2><p className="muted">직접 확인한 내용부터 적어 주세요. 모르는 항목은 비워 두고, 확인한 만큼 이어서 작성할 수 있습니다.</p></div>
    <form onSubmit={event => { event.preventDefault(); void d.assess(); }} noValidate>
      <Field name="summary" label="확인한 사실" multiline maxLength={1000} hint="직접 확인한 현상과 근거를 적으세요. 원시 로그, 비밀키, 개인별 정보는 넣지 마세요."/>
      <Field name="discoveredAt" label="문제를 인지한 시각 · 한국 시간" type="datetime-local" required hint="UTC+09:00 기준입니다. 검사 실행 시각과 사고를 알게 된 시각은 다를 수 있습니다."/>
      <fieldset className="incident-types"><legend>어떤 상황인가요? <span className="muted">여러 개 선택 가능</span></legend><div className="incident-type-options">{(Object.entries(incidentTypeLabels) as [IncidentType, string][]).map(([kind, label]) => <label className="incident-choice" key={kind}><input type="checkbox" checked={d.form.incidentTypes.includes(kind)} onChange={event => d.updateForm("incidentTypes", event.target.checked ? [...d.form.incidentTypes, kind] : d.form.incidentTypes.filter(value => value !== kind))}/><span>{label}</span></label>)}</div><p className="field-hint">선택이 어려우면 비워 두세요. 신고 안내에서 추가 확인이 필요한 항목으로 표시합니다.</p></fieldset>
      <Field name="actions" label="지금까지 취한 조치" multiline hint="실제로 한 조치를 한 줄에 하나씩 적어 주세요. 예: 노출된 키 폐기 후 재발급"/>
      <div className="incident-fields">
        <div className="form-field"><label htmlFor="incident-status">현재 대응 상태</label><select id="incident-status" value={d.form.incidentStatus} onChange={event => d.updateForm("incidentStatus", event.target.value as IncidentForm["incidentStatus"])}><option value="unknown">아직 확인하지 못했어요</option><option value="ongoing">대응 중</option><option value="contained">확산 차단</option><option value="recovered">복구 완료</option></select></div>
        <div className="form-field"><label htmlFor="incident-filingType">신고 구분</label><select id="incident-filingType" value={d.form.filingType} onChange={event => d.updateForm("filingType", event.target.value as IncidentForm["filingType"])}><option value="unknown">아직 확인하지 못했어요</option><option value="initial">최초 신고</option><option value="supplement">보완 신고</option></select></div>
      </div>
      <p className="field-hint">두 항목은 초안 생성 전에 확인해야 합니다. 모르면 미확인 상태로 신고 대상·기한부터 확인할 수 있습니다.</p>
      <div className="form-field"><label htmlFor="incident-leakState">개인정보 유출을 확인했나요?</label><select id="incident-leakState" value={d.form.leakState} onChange={event => d.updateForm("leakState", event.target.value as IncidentForm["leakState"])}><option value="unknown">아직 확인하지 못했어요</option><option value="none">현재 확인한 범위에서 유출 정황이 없어요</option><option value="suspected">유출이 의심돼요</option><option value="confirmed">유출 사실을 확인했어요</option></select><p className="field-hint">기관에 신고하는 일과 영향을 받은 분들께 통지하는 일은 별도로 확인합니다.</p></div>
      {hasPersonalInfo && <div className="incident-conditional"><h3>개인정보에 대해 확인한 내용</h3>
        <div className="incident-fields"><Field name="affectedCount" label="영향받은 인원" type="number" hint="모르면 비워 두세요. 빈칸은 0명이 아닙니다."/><Field name="personalItems" label="유출된 항목" hint="이메일, 이름처럼 항목명만 쉼표로 구분하세요."/></div>
        <label className="incident-choice"><input type="checkbox" checked={d.form.countIsEstimate} onChange={event => d.updateForm("countIsEstimate", event.target.checked)}/><span>인원은 추정치예요</span></label>
        <Answer name="includesSensitive" label="민감정보가 포함됐나요?" hint="예: 건강, 정치적 견해 등"/>
        <Answer name="includesUniqueId" label="고유식별정보가 포함됐나요?" hint="예: 주민등록번호, 여권번호 등"/>
        <Answer name="externalAccess" label="외부의 불법 접근으로 유출됐나요?"/>
        <Answer name="recoveredLowRisk" label="유출 정보를 회수·삭제해 피해 가능성이 현저히 낮아졌나요?" hint="단순히 취약점을 수정한 것과는 다릅니다. 확인한 경우에만 예를 선택하세요."/>
        <Answer name="subjectsNotified" label="영향받은 분들께 이미 통지했나요?"/>
        {d.form.subjectsNotified === "yes" && <div className="incident-fields"><Field name="notifiedAt" label="통지한 시각 · 한국 시간" type="datetime-local"/><Field name="notifyMethod" label="통지 방법" maxLength={200}/></div>}
      </div>}
      <details className="incident-disclosure"><summary>기관·담당자와 사고 상세 보완 <span className="muted">제출 전 확인</span></summary>
        <div className="incident-fields"><Field name="organizationName" label="회사·기관명" maxLength={200}/><Field name="serviceName" label="서비스명" maxLength={200}/></div>
        <Field name="occurredAt" label="확인한 사고 발생 시각 · 한국 시간" type="datetime-local" hint="발생 시각을 모르면 비워 두세요. 인지 시각과 구분합니다."/>
        <Field name="cause" label="확인한 원인" multiline maxLength={2000} hint="추측은 구분해서 적으세요. 선택한 검사 발견으로 제안된 원인은 문서에서 별도로 표시합니다."/>
        <Field name="damage" label="확인한 피해 내용" multiline maxLength={2000}/>
        <div className="incident-fields"><Field name="department" label="담당 부서" maxLength={100}/><Field name="contactName" label="담당자" maxLength={50}/><Field name="contactPhone" label="연락처" type="tel" maxLength={30}/><Field name="contactEmail" label="이메일" type="email" maxLength={200}/></div>
      </details>
      <Evidence/>
      {d.errors.assessment && <p className="form-error" role="alert">{d.errors.assessment}</p>}
      <div className="incident-actions"><button className="button primary" type="submit" disabled={d.busy.assessment}>{d.busy.assessment ? <LoaderCircle className="spin" size={16}/> : <ArrowRight size={16}/>}신고 대상·기한 확인</button></div>
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

function Duties() {
  const d = useIncident();
  const stale = d.assessment?.revision !== d.revision;
  return <section className="incident-duties" aria-labelledby="incident-duties-title">
    <div className="incident-panel-intro"><p className="eyebrow">02 · SEPARATE DUTIES</p><h2 id="incident-duties-title">필요한 대응을 각각 확인하세요.</h2><p className="muted">입력한 내용에 따른 안내입니다. 모르는 사실이 남아 있으면 추가 확인이 필요합니다.</p></div>
    {stale && <Notice compact>사실 기록이 변경됐습니다. 이전 안내와 기한을 사용하기 전에 다시 확인해 주세요.</Notice>}
    {d.assessment?.result.needs.map(need => {
      const gaps = getAssessmentGaps(d.form, need.kind);
      const incomplete = !need.required && gaps.length > 0;
      return <article className="card incident-duty" key={need.kind}>
        <div className="incident-duty-heading"><span className="incident-hour">{need.kind === "incident_24h" ? "24h" : "72h"}</span><div><p className="eyebrow">{need.kind === "incident_24h" ? "KISA · 침해사고" : "개인정보보호위원회 · 유출 신고"}</p><h3>{need.kind === "incident_24h" ? "침해사고 신고" : "개인정보 유출 신고"}</h3></div></div>
        <span className={`incident-status ${need.required && !stale ? "needs-action" : ""}`}>{stale ? "입력 변경 · 다시 확인" : need.required ? "신고 대상 안내 · 적용 범위 확인" : incomplete ? "추가 사실 확인 필요" : "입력 기준 신고 요건 미확인"}</span>
        {!stale && <><ul className="incident-bullets">{(incomplete ? gaps : need.reasons).map(reason => <li key={reason}>{reason}</li>)}</ul>{need.required && !!gaps.length && <p className="field-hint">아직 확인하지 못한 내용도 있습니다. 사고 기록을 계속 보완하세요.</p>}{need.deadline && <DeadlineView key={`${need.kind}:${need.deadline.due_at}:${d.assessment?.revision}`} deadline={need.deadline}/>}</>}
        <p className="fine-print">{need.kind === "incident_24h" ? "정보통신서비스 제공자 등 법정 적용 대상인지 공식 안내에서 함께 확인하세요." : "기관 신고의 안내입니다. 정보주체 통지 여부는 별도로 확인하세요."}</p>
      </article>;
    })}
    <article className="card incident-duty incident-notification"><div className="panel-heading"><ShieldAlert size={21}/><h3>정보주체 통지</h3></div><span className="incident-status">공식 기준 확인 필요</span><p>기관에 신고하는 일과 영향을 받은 분들께 알리는 일은 별도입니다. 실제 유출 통지와 유출 가능성 통지는 적용 조건과 기산점이 다릅니다.</p><p className="muted">현재 도우미는 통지 의무를 자동 판정하지 않습니다. 생성되는 통지문도 사실관계와 최신 요건을 확인해야 하는 검토용 초안입니다.</p><OfficialLink href={official.law}>현행 통지·신고 기준 확인</OfficialLink></article>
    <div className="incident-actions"><button className="button secondary" onClick={() => d.setStep(0)}><ArrowLeft size={16}/>사실 보완하기</button>{stale ? <button className="button primary" disabled={d.busy.assessment} onClick={() => void d.assess()}>{d.busy.assessment && <LoaderCircle className="spin" size={16}/>}다시 확인</button> : <button className="button primary" onClick={() => d.setStep(2)}>문서·제출 준비<ArrowRight size={16}/></button>}</div>
    {d.errors.assessment && <p className="form-error" role="alert">{d.errors.assessment}</p>}
  </section>;
}

function ReportFields({ fields }: { fields: ReportField[] }) {
  return <dl className="incident-report-fields">{fields.map((field, index) => <div key={`${field.label}:${index}`}><dt>{field.label}{field.auto && <span className="incident-provenance">자동 제안 · 확인 필요</span>}{field.required && !field.value && <span className="incident-provenance">미입력</span>}</dt><dd>{field.value || "확인 중 · 제출 전 보완"}{field.hint && <small>{field.hint}</small>}</dd></div>)}</dl>;
}

function ReportSections({ sections }: { sections: ReportSection[] }) {
  return <div className="incident-report-sections">{sections.map((section, index) => <details key={`${section.heading}:${index}`}><summary>{section.heading}</summary>{section.paragraphs.map((paragraph, i) => <p key={i}>{paragraph}</p>)}<ReportFields fields={section.fields}/><ul className="incident-bullets">{section.bullets.map((line, i) => <li key={i}>{line}</li>)}</ul><ol className="incident-bullets">{section.steps.map((line, i) => <li key={i}>{line}</li>)}</ol>{section.cards.map((card, i) => <div className="incident-report-card" key={i}><h3>{card.title}</h3>{card.badges.map((badge, j) => <span className="incident-provenance" key={j}>{badge.text}</span>)}{card.paragraphs.map((paragraph, j) => <p key={j}>{paragraph}</p>)}<ReportFields fields={card.fields}/><ol className="incident-bullets">{card.steps.map((line, j) => <li key={j}>{line}</li>)}</ol></div>)}</details>)}</div>;
}

function DocumentEditor({ kind }: { kind: FilingKind }) {
  const d = useIncident();
  const doc = d.documents[kind];
  const stale = !!doc && doc.revision !== d.revision;
  const [replace, setReplace] = useState(false);
  const [html, setHtml] = useState<{ source: typeof doc; content: string } | null>(null);
  const [htmlBusy, setHtmlBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [htmlError, setHtmlError] = useState("");
  const sequence = useRef(0);
  const clipboard = useClipboard();
  useEffect(() => () => { sequence.current++; }, []);
  const output = doc ? `> ${reviewNotice}\n> 공식 안내: ${official.incident}\n> 개인정보 신고: ${official.privacy}\n> 통지·신고 기준: ${official.law}\n\n${doc.markdown}` : "";
  function generate() {
    clipboard.clearFeedback(); setFeedback(""); setHtmlError("");
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
  async function preview() {
    if (!doc || htmlBusy) return;
    const token = ++sequence.current;
    setHtmlBusy(true); setHtmlError("");
    try {
      const content = await getFilingDocument(doc.body, kind, "html");
      if (token === sequence.current) setHtml({ source: doc, content });
    } catch (caught) {
      if (token === sequence.current) setHtmlError(caught instanceof Error ? caught.message : "HTML 초안을 가져오지 못했습니다.");
    } finally { if (token === sequence.current) setHtmlBusy(false); }
  }
  return <article className="card incident-document" aria-labelledby={`${kind}-title`}>
    <div className="incident-duty-heading"><FileText size={22}/><div><p className="eyebrow">{kind === "incident_24h" ? "24 HOURS · KISA" : "72 HOURS · PRIVACY"}</p><h3 id={`${kind}-title`}>{filingNames[kind]}</h3></div></div>
    <p className="muted">{kind === "incident_24h" ? "공통 사고 기록으로 침해사고 신고 초안을 준비합니다." : "동일한 사실과 조치를 재사용합니다. 신고서와 정보주체 통지문을 구분해 검토하세요."}</p>
    {kind === "privacy_72h" && d.form.leakState !== "confirmed" && <p className="incident-document-warning">유출 사실이 확정되지 않았습니다. 생성된 문서가 유출을 확정한 표현을 포함하는지 확인하고, 의심 내용을 사실로 제출하지 마세요.</p>}
    <div className="incident-actions"><button className="button secondary" disabled={d.busy[kind]} onClick={generate}>{d.busy[kind] ? <LoaderCircle className="spin" size={16}/> : <FileText size={16}/>} {doc ? "현재 사실로 다시 만들기" : "검토용 초안 만들기"}</button>{doc && <span className="incident-status">{stale ? "입력 변경 · 갱신 필요" : doc.edited ? "직접 편집한 초안" : "초안 생성 · 접수 전"}</span>}</div>
    {replace && <div className="incident-replace" role="alert"><p>다시 만들면 이 문서에서 직접 편집한 내용이 현재 사실 기록으로 교체됩니다. 다른 신고서의 편집 내용은 유지됩니다.</p><button className="button secondary" onClick={() => setReplace(false)}>편집 내용 유지</button><button className="button primary" onClick={() => { setReplace(false); void d.generate(kind, true); }}>현재 사실로 교체</button></div>}
    {d.errors[kind] && <p className="form-error" role="alert">{d.errors[kind]}</p>}
    {doc && <>
      {stale && <Notice compact>공통 사실이 변경됐습니다. 이 문서의 편집 내용은 보존했습니다. 사실 기록을 반영해 다시 만든 뒤 복사·다운로드하세요.</Notice>}
      <div className="incident-missing"><h4>제출 전에 보완할 항목 <span>{doc.report.missing.length}개</span></h4>{doc.report.missing.length ? <ul className="incident-bullets">{doc.report.missing.map(label => <li key={label}>{label}</li>)}</ul> : <p>필수 칸이 채워졌습니다. 사실관계·신고 대상·최신 서식과 통지 의무는 별도로 확인하세요.</p>}<p className="fine-print">생성 당시 입력 기준입니다. 아래 문장을 직접 편집해도 확인 목록은 자동 판정되지 않습니다.</p></div>
      <details className="incident-disclosure"><summary>항목별 원본과 자동 제안 확인</summary><p className="field-hint">사용자 입력과 자동 제안의 출처를 구분해 검토하세요. 아래 내용은 생성 당시 원본입니다.</p><ReportSections sections={doc.report.sections}/></details>
      <div className="form-field incident-editor"><label htmlFor={`draft-${kind}`}>편집 가능한 Markdown 초안</label><textarea id={`draft-${kind}`} rows={15} value={doc.markdown} onChange={event => { d.editDocument(kind, event.target.value); clipboard.clearFeedback(); setFeedback(""); }} aria-describedby={`draft-${kind}-hint`}/><p className="field-hint" id={`draft-${kind}-hint`}>직접 편집한 내용은 복사·다운로드에 반영됩니다. 비밀키와 불필요한 개인정보는 포함하지 마세요.</p></div>
      <p className="incident-document-warning">{reviewNotice}</p>
      <div className="incident-actions"><button className="button secondary" disabled={stale || !doc.markdown.trim()} onClick={() => { setFeedback(""); void clipboard.copy(output); }}><Clipboard size={15}/>편집한 초안 복사</button><button className="button secondary" disabled={stale || !doc.markdown.trim()} onClick={download}><Download size={15}/>Markdown 다운로드</button><button className="text-link" disabled={stale || htmlBusy} onClick={() => void preview()}>{htmlBusy ? "원본 불러오는 중…" : "생성 당시 원본 HTML 보기"}<ChevronRight size={14}/></button></div>
      <p className="feedback" role="status">{clipboard.feedback || feedback}</p>{htmlError && <p className="form-error" role="alert">{htmlError}</p>}
      {html?.source === doc && !stale && <div className="incident-html"><p className="field-hint">생성 당시 원본입니다. 위에서 직접 편집한 내용은 포함되지 않습니다. 인쇄·제출 전 최신 법령과 내용을 확인하세요.</p><iframe title={`${filingNames[kind]} 생성 원본`} srcDoc={html.content} sandbox=""/></div>}
      <div className="incident-destination"><h4>공식 제출처 안내</h4><ul className="incident-bullets">{doc.report.submit_to.map(line => <li key={line}>{line}</li>)}</ul><OfficialLink href={kind === "incident_24h" ? official.incident : official.privacy}>공식 신고 안내 열기</OfficialLink>{doc.report.disclaimer && <p className="fine-print">{doc.report.disclaimer}</p>}</div>
    </>}
  </article>;
}

function Documents() {
  const d = useIncident();
  return <section aria-labelledby="incident-documents-title"><div className="incident-panel-intro"><p className="eyebrow">03 · PREPARE TO FILE</p><h2 id="incident-documents-title">공통 사실로, 필요한 문서를.</h2><p className="muted">두 신고서에 같은 사고 기록을 사용합니다. 문서를 생성해도 기관 접수나 정보주체 통지가 이루어지지는 않습니다.</p></div><Notice compact>{reviewNotice}</Notice><div className="incident-documents"><DocumentEditor kind="incident_24h"/><DocumentEditor kind="privacy_72h"/></div><div className="incident-actions"><button className="button secondary" onClick={() => d.setStep(1)}><ArrowLeft size={16}/>신고 안내로</button><button className="text-link" onClick={() => d.setStep(0)}>사실 기록 보완하기<ArrowRight size={15}/></button></div></section>;
}

export default function IncidentWorkspace() {
  const d = useIncident();
  const heading = useRef<HTMLDivElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: "start" }); }, [d.step]);
  const labels = ["사실 입력", "신고 대상·기한", "문서·제출 준비"];
  return <div className="incident-workspace">
    <nav className="incident-steps" aria-label="사고 신고 지원 단계"><ol>{labels.map((label, index) => <li key={label}><button aria-current={d.step === index ? "step" : undefined} disabled={index > 0 && !d.assessment} onClick={() => d.setStep(index)}><span>{d.step > index ? <Check size={14}/> : `0${index + 1}`}</span><strong>{label}</strong></button></li>)}</ol></nav>
    <div ref={heading} tabIndex={-1} className="incident-step-content" aria-label={labels[d.step]}>{d.step === 0 ? <Facts/> : d.step === 1 ? <Duties/> : <Documents/>}</div>
  </div>;
}
