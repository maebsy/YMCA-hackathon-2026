"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Clipboard, Code2, Download, FileText, LoaderCircle, Play, ShieldAlert } from "lucide-react";
import { WorkspaceTab } from "@/components/tabs/WorkspaceTab";
import { normalizeRepositoryUrl, useRepository } from "@/components/repository-provider";
import { Notice } from "@/components/ui/notice";
import { useClipboard } from "@/components/ui/clipboard";
import { plainReport } from "@/lib/api";
import type { Hosting, OS } from "@/types/security";

function ActualReport() {
  const repository = useRepository();
  const clipboard = useClipboard();
  const [html, setHtml] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [clipboardFor, setClipboardFor] = useState(repository.reportInput);
  const [error, setError] = useState("");
  const operation = useRef(0);
  useEffect(() => {
    const lifecycle = operation;
    operation.current++;
    // A report belongs to one engine result; clear it when that result changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHtml(""); setMarkdown(""); setFeedback(""); setError(""); setBusy(false);
    return () => { lifecycle.current++; };
  }, [repository.reportInput]);
  async function request(action: "html" | "copy" | "download") {
    if (!repository.reportInput || repository.isScanning || busy) return;
    const token = ++operation.current;
    setBusy(true); setError(""); setFeedback(""); clipboard.clearFeedback();
    try {
      const format = action === "html" ? "html" : "markdown";
      const content = await plainReport(repository.reportInput, format);
      if (token !== operation.current) return;
      if (action === "html") { setHtml(content); setFeedback("실제 검사 결과로 HTML 리포트를 만들었습니다."); }
      else {
        setMarkdown(content);
        if (action === "copy") { setClipboardFor(repository.reportInput); await clipboard.copy(content); }
        else {
          const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
          const anchor = document.createElement("a");
          anchor.href = url; anchor.download = "72hours-repository-report.md";
          try { document.body.appendChild(anchor); anchor.click(); setFeedback("Markdown 다운로드를 요청했습니다."); }
          finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
        }
      }
    } catch (caught) {
      if (token === operation.current) setError(caught instanceof Error ? caught.message : "리포트를 만들지 못했습니다.");
    } finally { if (token === operation.current) setBusy(false); }
  }
  const disabled = !repository.reportInput || repository.isScanning || busy;
  return <section className="card repository-report" aria-labelledby="repository-report-title">
    <div className="panel-heading"><FileText size={22}/><h2 id="repository-report-title">실제 검사 리포트</h2></div>
    <p className="muted">엔진이 반환한 검사 범위와 발견 항목으로 서버에서 문서를 생성합니다. 수동 조치 표시는 해결 검증에 포함되지 않습니다.</p>
    {!repository.reportInput && <p className="field-hint">검사를 완료하면 HTML 미리 보기와 Markdown을 사용할 수 있습니다.</p>}
    <div className="report-actions">
      <button className="button primary" disabled={disabled} onClick={() => void request("html")}><FileText size={16}/>HTML 리포트 보기</button>
      <button className="button secondary" disabled={disabled} onClick={() => void request("copy")}><Clipboard size={16}/>Markdown 복사</button>
      <button className="button secondary" disabled={disabled} onClick={() => void request("download")}><Download size={16}/>Markdown 다운로드</button>
    </div>
    <p className="feedback" role="status">{busy ? "리포트를 생성하고 있습니다…" : (clipboardFor === repository.reportInput ? clipboard.feedback : "") || feedback}</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {html && <iframe className="repository-report-frame" title="실제 저장소 검사 리포트" srcDoc={html} sandbox=""/>}
    {markdown && <details><summary>Markdown 원문 직접 복사하기</summary><pre className="repository-markdown" tabIndex={0}>{markdown}</pre></details>}
  </section>;
}

export default function RepositoryWorkspace() {
  const repository = useRepository();
  const input = useRef<HTMLInputElement>(null);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!normalizeRepositoryUrl(repository.repoInput)) input.current?.focus();
    void repository.runScan();
  }
  const verified = repository.findings.filter(finding => finding.fixed).length;
  const pending = repository.pendingIds.length;
  return <main id="main" className="workspace container repository-page" tabIndex={-1}>
    <div className="page-heading"><p className="eyebrow">REPOSITORY · ENGINE SCAN</p><h1>내 저장소를 실제로 점검하세요.</h1><p>공개 GitHub 저장소를 엔진으로 검사하고, 근거와 수정 안내를 확인합니다.</p></div>
    <Notice>실행하면 저장소 주소가 검사 서버로 전송됩니다. 서버의 로그인·저장소 접근 정책이 적용됩니다. 공개 저장소만 입력하세요. 웹사이트 주소만으로 서버 코드나 DB를 검사하지 않습니다.</Notice>
    <section className="card form-card repository-input" aria-labelledby="repository-input-title">
      <div className="panel-heading"><Code2 size={22}/><h2 id="repository-input-title">공개 GitHub 저장소</h2></div>
      <form onSubmit={submit} noValidate>
        <div className="form-field"><label htmlFor="repository-url">저장소 URL</label><div className="url-form-row"><div className="url-field"><Code2 size={19}/><input ref={input} id="repository-url" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" placeholder="https://github.com/owner/repository" value={repository.repoInput} onChange={event => repository.setRepoInput(event.target.value)} disabled={repository.isScanning} aria-invalid={!!repository.error} aria-describedby="repository-hint repository-error"/></div><button className="button primary" type="submit" disabled={!repository.restored || repository.isScanning}>{repository.isScanning ? <LoaderCircle className="spin" size={16}/> : <Play size={16}/>} {repository.isScanning ? "검사 진행 중" : "실제 검사 시작"}</button></div><p id="repository-hint" className="field-hint">저장소 루트 주소를 사용하세요. 로그인, 파일 경로, 쿼리는 받지 않습니다. 검사와 추가 AI 해석은 수 분 걸릴 수 있습니다.</p></div>
        {repository.error && <p id="repository-error" className="form-error" role="alert">{repository.error}</p>}
        <div className="repository-environment">
          <fieldset><legend>수정 안내에 사용할 OS</legend><div className="chip-row">{([["windows", "Windows"], ["macos", "macOS"], ["linux", "Linux"]] as [OS, string][]).map(([os, label]) => <button key={os} type="button" className={`os-chip ${repository.os === os ? "active-chip" : ""}`} aria-pressed={repository.os === os} disabled={repository.isScanning} onClick={() => repository.setOS(os)}>{label}</button>)}</div></fieldset>
          <fieldset><legend>호스팅 환경</legend><div className="chip-row">{([["vercel", "Vercel"], ["netlify", "Netlify"], ["unknown", "직접 운영 / 모름"]] as [Hosting, string][]).map(([host, label]) => <button key={host} type="button" className={`host-chip ${repository.hosting === host ? "active-chip" : ""}`} aria-pressed={repository.hosting === host} disabled={repository.isScanning} onClick={() => repository.setHosting(host)}>{label}</button>)}</div></fieldset>
        </div>
      </form>
    </section>
    <p className="feedback" role="status">{repository.message}</p>
    {repository.result && <>
      <div className="result-context"><span className="status-label">실제 엔진 결과 · 브라우저 보관</span><code>{repository.resultRepo}</code><p>아래 결과는 위 저장소의 마지막 검사입니다. 다른 저장소를 입력해도 새 검사가 완료되기 전에는 이 결과를 유지합니다.</p></div>
      <dl className="count-grid"><div><dt>엔진 발견 항목</dt><dd>{repository.findings.length}<small>건</small></dd></div><div><dt>미해결 · 미조치</dt><dd>{repository.findings.length - verified - pending}<small>건</small></dd></div><div><dt>재검증 대기</dt><dd className="accent">{pending}<small>건</small></dd></div><div><dt>엔진 해결 확인</dt><dd>{verified}<small>건</small></dd></div></dl>
    </>}
    <div className="legacy-workspace"><WorkspaceTab compact hasRealScan={!!repository.result} hasResult={!!repository.result} pendingIds={repository.pendingIds} findings={repository.findings}
      onToggleFindingFixed={repository.togglePending} selectedFindingId={repository.selectedFindingId} onSelectFindingId={repository.selectFinding}
      logs={repository.logs} onRunScan={url => { void repository.runScan(url); }} isScanning={repository.isScanning}
      os={repository.os} onChangeOS={repository.setOS} hosting={repository.hosting} onChangeHosting={repository.setHosting} countdown=""
      onShowToast={repository.showMessage} repoInput={repository.repoInput} onChangeRepoInput={repository.setRepoInput}/></div>
    <Notice compact>수정 명령은 자동 실행하지 않습니다. 직접 조치한 항목은 ‘재검증 대기’로 표시하고 같은 저장소를 다시 검사하세요. 엔진의 코드 해결 상태만 ‘해결 확인’으로 집계합니다. 검사 결과와 조치 표시는 이 브라우저에 저장됩니다.</Notice>
    <ActualReport/>
    <section className="card incident-entry"><ShieldAlert size={22}/><div><h2>실제 사고가 의심되나요?</h2><p className="muted">확인한 사실을 기록하고 신고 대상·기한과 두 신고서 초안을 준비하세요. 검사 발견은 선택해서 연결할 수 있습니다.</p><Link className="text-link" href="/incident">사고 신고 준비하기 <ArrowRight size={15}/></Link></div></section>
    <Link className="text-link" href="/"><ArrowLeft size={15}/>GitHub 주소 입력으로 돌아가기</Link>
  </main>;
}
