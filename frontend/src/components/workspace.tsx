"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, CircleHelp, Clipboard, FileText, ShieldAlert } from "lucide-react";
import { useIncident } from "./incident-provider";
import { Notice } from "./ui/notice";
import { useClipboard } from "./ui/clipboard";

type View = "incident" | "help";
const titles: Record<View, [string, string, string]> = {
  incident: ["OPTIONAL · INCIDENT NOTES", "확인한 사실부터, 차분하게.", "침해가 의심될 때 직접 확인한 사실을 기록하고 검토용 초안을 만드세요."],
  help: ["HELP & SCOPE", "시작하기 전에 알아두세요.", "GitHub 저장소 검사부터 수정 안내와 결과 전달까지 안내합니다."],
};
function Incident() {
  const d = useIncident();
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
  return <><Notice>빈 양식에 직접 확인한 사실만 입력하세요. 입력 내용은 외부로 전송되지 않으며 새로고침하면 사라집니다.</Notice><div className="incident-layout"><section className="card form-card"><div className="panel-heading"><FileText size={22}/><h2>사실 기록</h2></div><form onSubmit={generate} noValidate>{fields.map(([key, label, placeholder]) => <div className="form-field" key={key}><label htmlFor={`incident-${key}`}>{label}{key !== "action" && <span className="accent" aria-label="필수"> *</span>}</label>{key === "observation" || key === "action" ? <textarea id={`incident-${key}`} rows={key === "observation" ? 5 : 3} placeholder={placeholder} value={d.facts[key]} onChange={e => d.setFacts({ ...d.facts, [key]: e.target.value })} required={key !== "action"}/> : <input id={`incident-${key}`} type={key === "date" ? "datetime-local" : "text"} placeholder={placeholder} value={d.facts[key]} onChange={e => d.setFacts({ ...d.facts, [key]: e.target.value })} required/>}</div>)}{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary" type="submit">{d.draft ? "입력한 사실로 초안 다시 만들기" : "검토용 초안 만들기"}<ArrowRight size={16}/></button>{d.draft && <p className="field-hint">다시 만들면 편집 중인 초안이 위 사실 기록으로 교체됩니다.</p>}</form></section><section className="card draft-card"><div className="panel-heading"><h2>대응 초안</h2><span className="status-label">직접 편집 가능</span></div><p className="muted">작성 후 사실관계를 검토하세요. 신고를 제출하지 않습니다.</p><label className="sr-only" htmlFor="incident-draft">편집 가능한 대응 초안</label><textarea id="incident-draft" value={d.draft} onChange={e => { d.setDraft(e.target.value); setGenerated(""); clipboard.clearFeedback(); }} placeholder="확인한 사실을 입력하면 이곳에 초안이 만들어집니다." rows={19}/><button className="button secondary" disabled={!d.draft.trim()} onClick={() => clipboard.copy(d.draft)}><Clipboard size={15}/>초안 복사</button><p className="feedback" role="status">{clipboard.feedback || generated}</p><p className="fine-print">민감한 정보와 인증정보는 입력하지 마세요. 법적 판단이나 신고 의무는 전문가에게 확인하세요.</p></section></div></>;
}

function Help() {
  return <div className="help-layout">
    <section className="help-content">
      <article className="card">
        <CircleHelp size={24} className="accent"/><h2>GitHub 주소로 시작하고, 한 단계씩.</h2>
        <ol className="repair-steps">
          <li><span>1</span><div><h3>공개 GitHub 저장소 입력</h3><p>홈에서 https://github.com/owner/repository 형식의 저장소 루트 주소를 입력하세요. 파일 경로, 로그인 정보, 쿼리와 해시가 있는 주소는 받지 않습니다. 실행하면 저장소 주소를 검사 서버로 보냅니다.</p></div></li>
          <li><span>2</span><div><h3>엔진 검사와 추가 AI 해석</h3><p>실제 검사 화면에서 진행 로그와 도구별 실행 범위를 확인하세요. GPU 해석 서버를 사용할 수 있으면 상위 발견 항목에 Red–Blue 해석을 더합니다. 추가 해석이 실패해도 엔진 결과는 유지합니다.</p></div></li>
          <li><span>3</span><div><h3>근거 확인과 수정</h3><p>발견 항목을 선택하면 관찰 근거와 수정 안내를 볼 수 있습니다. 직접 조치한 항목은 ‘재검증 대기’로 표시하고, 같은 저장소를 다시 검사해 이전 결과와 비교하세요.</p></div></li>
          <li><span>4</span><div><h3>MCP 전달과 리포트</h3><p>검사 결과를 파일로 저장하고 MCP 설정을 복사해 AI 코딩 도구에 연결할 수 있습니다. 전달 가능 건수와 차단 사유를 확인하세요. 실제 검사 데이터로 HTML 리포트와 Markdown 문서도 만듭니다.</p></div></li>
        </ol>
      </article>
      <article className="card">
        <h2>검사 범위와 결과 보관</h2>
        <p><Link className="text-link" href="/repository">검사 결과와 진행 상황 보기 <ArrowRight size={14}/></Link></p>
        <dl className="help-definitions">
          <div><dt>검사 대상과 접근 권한</dt><dd>공개 GitHub 저장소를 검사합니다. 서버 설정에 따라 로그인과 허용된 저장소 소유자 권한이 필요할 수 있습니다. 접근이 거절되면 로그인 상태와 해당 저장소의 검사 허용 여부를 확인하세요. 일반 웹사이트 주소만으로 서버 코드나 DB를 검사하지 않습니다.</dd></div>
          <div><dt>엔진 결과와 추가 해석</dt><dd>도구가 실제로 실행한 범위와 관찰 근거를 먼저 확인하세요. AI 해석이나 발견 항목이 없다는 사실만으로 서비스 전체가 안전하다고 판단할 수 없습니다. 추가 AI 해석을 사용할 수 없어도 엔진 결과와 기본 안내는 남습니다.</dd></div>
          <div><dt>브라우저에 남는 결과</dt><dd>마지막 검사 결과와 수동 조치 표시를 이 브라우저에 저장해 새로고침 후 복원합니다. 다른 저장소를 입력해도 새 검사가 완료되기 전에는 이전 결과를 유지하므로 결과에 표시된 저장소를 확인하세요. 브라우저 저장소를 지우면 복원할 수 없습니다.</dd></div>
          <div><dt>MCP 파일과 설정</dt><dd>지원하는 브라우저에서는 자동 저장을 켤 수 있습니다. 지원하지 않으면 결과 파일을 내려받아 같은 이름으로 저장하세요. 설정의 사용자 경로와 설치 위치를 확인한 뒤 AI 코딩 도구에 연결하고, 전달 가능 항목과 제한을 검토하세요.</dd></div>
          <div><dt>문서와 사고 사실 기록</dt><dd>복사 성공 여부는 브라우저 권한에 따라 안내합니다. 사고 사실 기록은 빈 양식에 직접 입력하며 화면 이동 동안 유지되고 새로고침하면 사라집니다. 화면에서 수정 명령을 자동 실행하거나 사고 신고를 제출하지 않습니다.</dd></div>
        </dl>
      </article>
    </section>
    <aside className="card help-aside">
      <ShieldAlert size={25} className="accent"/><h3>조치 표시와 검증은 달라요.</h3>
      <p className="muted">수동 조치는 재검증 대기입니다. 엔진이 반환한 코드 해결 상태만 ‘해결 확인’으로 집계합니다. 실제 코드와 배포 환경에서 정상 기능도 함께 확인하세요.</p>
      <Link className="button primary" href="/">저장소 검사 시작하기 <ArrowRight size={16}/></Link>
      <Link className="text-link" href="/incident">사고 사실 기록하기 <ArrowRight size={15}/></Link>
    </aside>
  </div>;
}

export default function Workspace({ view }: { view: View }) {
  const [eyebrow, title, description] = titles[view];
  return <main id="main" className="workspace container" tabIndex={-1}>
    <Link className="back-link" href={view === "incident" ? "/repository" : "/"}><ArrowLeft size={14}/>{view === "incident" ? "검사 결과로" : "저장소 입력으로"}</Link>
    <div className="workspace-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
    {view === "incident" ? <Incident/> : <Help/>}
  </main>;
}
