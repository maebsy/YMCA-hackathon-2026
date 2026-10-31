"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Clipboard, Download, FileText, FlaskConical, ShieldAlert } from "lucide-react";
import { WorkspaceTab } from "@/components/tabs/WorkspaceTab";
import { useRepository } from "@/components/repository-provider";
import { mountReportDocument, reportDocumentHtml } from "@/lib/report-document";
import ReportScorecard from "@/components/report-scorecard";
import { scoreRows } from "@/lib/report-scorecard";
import { REPOSITORY_PROGRESS_PATH } from "@/lib/repository-routes";

// 진행 화면(scan-progress의 explainedText)과 같은 문구. 해석 1건이 몇 분 걸려 완료 수만 보면 멈춘 것처럼 보입니다
function explainedText(e: { done: number; total: number; running?: number; queued?: number }): string {
  return [`완료 ${e.done}/${e.total}건`, e.running ? `해석 중 ${e.running}` : "", e.queued && e.done < e.total ? `대기 ${e.queued}` : ""].filter(Boolean).join(" · ");
}
import "./repository-result.css";

export function RepositoryReport() {
  const repository = useRepository();
  const [feedback, setFeedback] = useState("");
  const active = useRef(0);
  const documentCleanup = useRef<(() => void) | undefined>(undefined);
  useEffect(() => () => { documentCleanup.current?.(); }, []);
  useEffect(() => () => { active.current++; }, []);
  const { reportInput, reportHtml, reportError, isScanning, prepareReport } = repository;
  // A restored result has no persisted document. Generate once; failures need an explicit retry.
  useEffect(() => {
    if (reportInput && !reportHtml && !reportError && !isScanning)
      void prepareReport();
  }, [reportInput, reportHtml, reportError, isScanning, prepareReport]);
  async function copy() {
    const token = ++active.current;
    try {
      // Call writeText in this user gesture, using the already prepared Markdown.
      await navigator.clipboard.writeText(repository.reportMarkdown);
      if (token === active.current) setFeedback("복사됨");
    } catch { if (token === active.current) setFeedback("복사 실패"); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([repository.reportMarkdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "72hours-repository-report.md";
    try { document.body.appendChild(anchor); anchor.click(); setFeedback("다운로드됨"); }
    finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  }
  return <section className="card repository-report" aria-labelledby="repository-report-title">
    <div className="repository-document-heading"><h2 id="repository-report-title"><FileText size={17}/>검사 리포트</h2>
      <div className="repository-document-actions"><span role="status">{feedback}</span>
        <button type="button" disabled={!repository.reportMarkdown || repository.isScanning} onClick={() => void copy()}><Clipboard size={13}/>MD 복사</button>
        <button type="button" disabled={!repository.reportMarkdown || repository.isScanning} onClick={download}><Download size={13}/>MD 다운로드</button>
      </div>
    </div>
    {repository.reportHtml ? <iframe className="repository-report-frame" title="실제 저장소 검사 리포트" srcDoc={reportDocumentHtml(repository.reportHtml)} sandbox="allow-same-origin" onLoad={event => {
      documentCleanup.current?.();
      // Same-origin access permits measuring; scripts remain blocked by sandbox.
      documentCleanup.current = mountReportDocument(event.currentTarget);
    }}/> :
      <p className="field-hint" role="status">{repository.isScanning ? "리포트를 만들고 있습니다…" : "리포트를 준비합니다."}</p>}
    {repository.reportError && <div className="form-error" role="alert"><p>{repository.reportError}</p><button type="button" className="text-link" disabled={repository.isScanning} onClick={() => void repository.prepareReport()}>다시 만들기</button></div>}
  </section>;
}

export default function RepositoryResult() {
  const repository = useRepository();
  const router = useRouter();
  const verified = repository.findings.filter(finding => finding.fixed).length;
  const pending = repository.pendingIds.length;
  function rescan(url = repository.resultRepo) {
    if (repository.isScanning) return;
    void repository.runScan(url);
    router.push(REPOSITORY_PROGRESS_PATH);
  }
  if (!repository.result) return <main id="main" className="workspace container repository-page" tabIndex={-1}>
    <h1 className="repository-small-title">검사 결과</h1>
    {repository.restored && <p className="field-hint">홈에서 검사할 GitHub 주소를 입력하세요. <Link className="text-link" href="/">홈으로 가기<ArrowRight size={14}/></Link></p>}
  </main>;
  return <main id="main" className="workspace container repository-page" tabIndex={-1}>
    <ReportScorecard key={`${repository.resultRepo}:${repository.startedAt ?? "restored"}`} rows={scoreRows(repository.reportInput?.findings ?? [], repository.findings, repository.pendingIds)}
      identity={`${repository.resultRepo}:${repository.startedAt ?? "restored"}`} fresh={repository.startedAt !== undefined && repository.phase === "done"}><RepositoryReport/></ReportScorecard>
    {repository.llmPending && <p className="field-hint" role="status">언어모델 쉬운 설명을 이어서 만드는 중입니다{repository.explained ? ` (${explainedText(repository.explained)})` : ""}. 끝나면 리포트와 취약점 상세에 자동으로 반영됩니다.</p>}
    <div className="repository-result-heading"><h1 className="repository-small-title">취약점 상세</h1><button className="button secondary" type="button" disabled={repository.isScanning} onClick={() => rescan()}>재검사</button></div>
    {/* The document does not include manual pending counts, so retain this breakdown below it. */}
    <dl className="count-grid"><div><dt>엔진 발견 항목</dt><dd>{repository.findings.length}<small>건</small></dd></div><div><dt>미해결 · 미조치</dt><dd>{repository.findings.length - verified - pending}<small>건</small></dd></div><div><dt>재검증 대기</dt><dd className="accent">{pending}<small>건</small></dd></div><div><dt>엔진 해결 확인</dt><dd>{verified}<small>건</small></dd></div></dl>
    <div className="legacy-workspace"><WorkspaceTab compact hasRealScan={!!repository.result} hasResult={!!repository.result} pendingIds={repository.pendingIds} findings={repository.findings}
      onToggleFindingFixed={repository.togglePending} selectedFindingId={repository.selectedFindingId} onSelectFindingId={repository.selectFinding}
      logs={repository.logs} onRunScan={url => rescan(url)} isScanning={repository.isScanning}
      os={repository.os} onChangeOS={repository.setOS} countdown=""
      onShowToast={repository.showMessage} repoInput={repository.repoInput} onChangeRepoInput={repository.setRepoInput}/></div>
    <section className="card incident-entry"><FlaskConical size={22}/><div><h2>고친 코드가 실제로 공격을 막을까요?</h2><p className="muted">Red가 공격하고 Blue가 고친 뒤, 격리 환경에서 수정 전·후를 직접 실행해 공격이 막히고 기능은 그대로인지 확인합니다. 지금은 데모 사이트로 시연하며, 내 저장소 실검증은 GitHub 로그인으로 소유권을 확인한 뒤 켭니다.</p><Link className="text-link" href="/verify">Red–Blue 실검증 보기 <ArrowRight size={15}/></Link></div></section>
    <section className="card incident-entry"><ShieldAlert size={22}/><div><h2>실제 사고가 의심되나요?</h2><p className="muted">확인한 사실을 기록하고 신고 대상·기한과 두 신고서 초안을 준비하세요. 검사 발견은 선택해서 연결할 수 있습니다.</p><Link className="text-link" href="/incident">사고 신고 준비하기 <ArrowRight size={15}/></Link></div></section>
    <Link className="text-link" href="/"><ArrowLeft size={15}/>GitHub 주소 입력으로 돌아가기</Link>
  </main>;
}
