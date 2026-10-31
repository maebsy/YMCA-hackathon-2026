"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ArrowRight, Code2, LoaderCircle, ShieldCheck, Sparkles, Unplug } from "lucide-react";
import { normalizeRepositoryUrl, useRepository } from "@/components/repository-provider";

export default function Home() {
  const repository = useRepository();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!repository.restored || repository.isScanning) return;
    const url = normalizeRepositoryUrl(repository.repoInput);
    if (!url) {
      setError("github.com/owner/repository 또는 owner.github.io 형식의 공개 GitHub 주소를 입력해 주세요.");
      input.current?.focus();
      return;
    }
    setError("");
    void repository.runScan(url);
    router.push("/repository");
  }
  return <main id="main" className="entry container" tabIndex={-1}>
    <div className="entry-intro">
      <p className="eyebrow"><span className="status-dot"/> SECURITY FOR BUILDERS</p>
      <h1>내 코드의 보안,<br/>GitHub 주소로 점검하세요.</h1>
      <p className="entry-description">실제 엔진으로 위험의 근거를 찾고,<br/>GPU Red–Blue 해석과 MCP로 다음 조치를 준비하세요.</p>
    </div>
    <section className="entry-panel card" aria-label="GitHub 저장소 실제 검사">
      <div className="entry-panel-top"><label htmlFor="repository">공개 GitHub 저장소</label></div>
      <form onSubmit={submit} noValidate>
        <div className="url-form-row">
          <div className="url-field"><Code2 size={20}/><input ref={input} id="repository" name="repository" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" placeholder="github.com/owner/repository 또는 owner.github.io" value={repository.repoInput} onChange={event => { repository.setRepoInput(event.target.value); if (error) setError(""); }} disabled={!repository.restored || repository.isScanning} aria-invalid={!!error} aria-describedby={error ? "repository-error repository-hint" : "repository-hint"}/></div>
          <button className="button primary" type="submit" disabled={!repository.restored || repository.isScanning}>{repository.isScanning ? <LoaderCircle className="spin" size={16}/> : null}{repository.isScanning ? "검사 진행 중" : "실제 검사 시작"}<ArrowRight size={16}/></button>
        </div>
        {error && <p id="repository-error" className="form-error" role="alert">{error}</p>}
        <p id="repository-hint" className="field-hint">github.com/owner/repository 또는 owner.github.io를 입력하세요. GitHub Pages는 해당 저장소로 변환해 검사합니다. 다른 도메인은 지원하지 않습니다.</p>
      </form>
      <div className="entry-disclosure"><ShieldCheck size={17}/><p><strong>주소를 검사 서버로 보내 실제 코드를 점검합니다.</strong><br/>서버의 로그인·저장소 접근 정책이 적용되며, 검사와 추가 AI 해석은 수 분 걸릴 수 있습니다.</p></div>
    </section>
    <div className="repository-entry"><Link className="text-link" href="/repository">{repository.isScanning ? "진행 중인 검사 보기" : "검사 환경과 저장된 결과 보기"}<ArrowRight size={14}/></Link></div>
    <p className="incident-home-entry"><Link className="text-link" href="/incident">사고가 의심되면, 검사 없이 신고 준비<ArrowRight size={14}/></Link></p>
    <p className="incident-home-entry"><Link className="text-link" href="/verify">고친 코드가 공격을 막는지 실제 실행으로 확인 (Red–Blue 실검증)<ArrowRight size={14}/></Link></p>
    <section className="entry-benefits" aria-label="실제 검사에서 다음 조치까지">
      <article><ShieldCheck size={20}/><h2>엔진으로 발견</h2><p>코드·의존성·비밀정보의<br/>실제 관찰 근거를 확인하세요.</p></article>
      <article><Sparkles size={20}/><h2>GPU로 해석</h2><p>연결 가능한 경우 Red–Blue가<br/>위험과 수정 방향을 설명합니다.</p></article>
      <article><Unplug size={20}/><h2>MCP로 전달</h2><p>결과를 코딩 도구에 전달하고<br/>수정 후 다시 검사하세요.</p></article>
    </section>
  </main>;
}
