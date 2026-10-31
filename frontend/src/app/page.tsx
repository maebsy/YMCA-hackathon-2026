"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ArrowRight, CheckCheck, Code2, Globe2, ShieldCheck } from "lucide-react";
import { useDemo } from "@/components/demo-provider";
import FlowSteps from "@/components/flow-steps";
import { validateWebsite } from "@/lib/sample";

export default function Home() {
  const demo = useDemo();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const website = validateWebsite(demo.website);
    if (!website) {
      setError("공개 도메인의 웹사이트 주소를 입력해 주세요. http(s) 주소만 가능하며 로그인 정보, 쿼리(?)와 해시(#)는 제외해 주세요.");
      input.current?.focus(); return;
    }
    setError(""); demo.setWebsite(website); demo.startSimulation(website); router.push("/scan");
  }
  return <main id="main" className="entry container" tabIndex={-1}>
    <div className="entry-intro"><p className="eyebrow"><span className="status-dot"/> SECURITY FOR BUILDERS</p><h1>내 서비스의 보안,<br/>URL 하나로 시작하세요.</h1><p className="entry-description">어디부터 고칠지 막막할 때.<br/>위험을 이해하고, 다음 조치를 정하는 첫 단계.</p></div>
    <section className="entry-panel card" aria-label="웹사이트 URL 입력">
      <div className="entry-panel-top"><label htmlFor="website">웹사이트 URL</label><span className="sample-label">샘플 체험</span></div>
      <form onSubmit={submit} noValidate>
        <div className="url-form-row"><div className="url-field"><Globe2 size={20}/><input ref={input} id="website" name="website" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="url" placeholder="https://my-service.com" value={demo.website} onChange={e => { demo.setWebsite(e.target.value); if (error) setError(""); }} aria-invalid={!!error} aria-describedby={error ? "website-error website-hint" : "website-hint"}/></div><button className="button primary" type="submit">점검 체험하기 <ArrowRight size={16}/></button></div>
        {error && <p id="website-error" className="form-error" role="alert">{error}</p>}
        <p id="website-hint" className="field-hint">도메인만 입력해도 됩니다. 예: my-service.vercel.app</p>
      </form>
      <div className="entry-disclosure"><ShieldCheck size={17}/><p><strong>웹사이트 URL은 샘플 체험용입니다.</strong><br/>입력한 사이트에 접속하지 않으며, 가상 서비스의 고정 샘플을 보여줍니다.</p></div>
    </section>
    <Link className="sample-shortcut text-link" href="/findings" onClick={demo.showSample}>URL 입력 없이 샘플 먼저 보기 <ArrowRight size={14}/></Link>
    <div className="repository-entry"><span>내 코드의 실제 결과가 필요하다면</span><Link className="text-link" href="/repository">GitHub 저장소 실제 검사 <ArrowRight size={14}/></Link></div>
    <FlowSteps step={1}/>
    <section className="entry-benefits" aria-label="체험에서 할 수 있는 일">
      <article><ShieldCheck size={20}/><h2>무엇부터 볼지</h2><p>위험의 근거와 우선순위를<br/>한눈에 살펴보세요.</p></article>
      <article><Code2 size={20}/><h2>어떻게 고칠지</h2><p>단계별 안내를 읽고<br/>AI 수정 요청을 준비하세요.</p></article>
      <article><CheckCheck size={20}/><h2>무엇을 확인할지</h2><p>수정 뒤에 직접 확인할<br/>체크리스트를 가져가세요.</p></article>
    </section>
  </main>;
}
