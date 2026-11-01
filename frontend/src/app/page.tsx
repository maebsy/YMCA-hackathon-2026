"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useRef, useState, useSyncExternalStore, type CSSProperties, type FormEvent } from "react";
import { ArrowRight, Code2, LoaderCircle, Pause, Play, ShieldCheck, Sparkles, Unplug } from "lucide-react";
import { normalizeRepositoryUrl, useRepository } from "@/components/repository-provider";
import { useRepoAutocomplete } from "@/lib/use-repo-autocomplete";
import { repositoryInputUrl, showGithubPrefix } from "@/lib/repo-suggest";
import McpConnect from "@/components/mcp-connect";
import "./repo-suggest.css";

const binaryStreams = Array.from({ length: 24 }, (_, column) =>
  Array.from({ length: 42 }, (_, row) => ((column * 7 + row * 3) % 11 < 5 ? "0" : "1")).join(""));

const noSubscribe = () => () => {};
const readMcpInline = () => new URLSearchParams(window.location.search).get("mcp") === "inline";

export default function Home() {
  const repository = useRepository();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [motionPaused, setMotionPaused] = useState(false);
  // 비교용 배치: /?mcp=inline 이면 MCP 연결을 검사 카드 안에 함께 보여 줍니다.
  const mcpInline = useSyncExternalStore(noSubscribe, readMcpInline, () => false);
  const autocomplete = useRepoAutocomplete({ value: repository.repoInput, setValue: repository.setRepoInput, inputRef: input });
  const prefixVisible = showGithubPrefix(repository.repoInput);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (repository.isScanning) {
      router.push("/repository");
      return;
    }
    if (!repository.restored) return;
    const url = normalizeRepositoryUrl(repositoryInputUrl(repository.repoInput));
    if (!url) {
      setError("owner/repository 또는 owner.github.io 형식의 공개 GitHub 주소를 입력해 주세요.");
      input.current?.focus();
      return;
    }
    setError("");
    void repository.runScan(url);
    router.push("/repository");
  }
  return <main id="main" className="entry container" tabIndex={-1}>
    <div className="entry-intro" data-paused={motionPaused ? "true" : undefined}>
      <div className="binary-background" aria-hidden="true">
        {binaryStreams.map((stream, index) => <div className="binary-column" key={index} style={{ "--column": index, "--duration": `${19 + index % 7 * 3}s`, "--delay": `${-index * 2.7}s` } as CSSProperties}><span>{stream}</span><span>{stream}</span></div>)}
      </div>
      <button className="hero-motion-toggle" type="button" aria-pressed={motionPaused} aria-label={motionPaused ? "숫자 배경 애니메이션 재생" : "숫자 배경 애니메이션 일시 정지"} onClick={() => setMotionPaused(value => !value)}>{motionPaused ? <Play size={13} aria-hidden="true"/> : <Pause size={13} aria-hidden="true"/>}<span>{motionPaused ? "배경 재생" : "배경 정지"}</span></button>
      <p className="eyebrow"><span className="status-dot"/> SECURITY FOR BUILDERS</p>
      <h1><span className="hero-title-line">내 코드의 <span className="hero-security-word">보안,</span></span><br/><span className="hero-title-accent">GitHub 주소로 점검하세요.</span></h1>
    </div>
    <section className="entry-panel card" aria-label="GitHub 저장소 실제 검사">
      <div className="entry-panel-top"><label htmlFor="repository">공개 GitHub 저장소</label></div>
      <form onSubmit={submit} noValidate>
        <div className="url-form-row">
          <div className="url-field rs-field"><Code2 size={20} aria-hidden="true"/>
            {prefixVisible && <span id="repository-prefix" className="rs-prefix" onClick={() => input.current?.focus()}>https://github.com/</span>}
            <input {...autocomplete.inputProps} ref={input} id="repository" name="repository" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" placeholder="owner/repository" onChange={event => { autocomplete.inputProps.onChange(event); if (error) setError(""); }} disabled={!repository.restored || repository.isScanning} aria-invalid={!!error} aria-describedby={[prefixVisible && "repository-prefix", error && "repository-error", "repository-hint"].filter(Boolean).join(" ")}/>
            <ul {...autocomplete.listProps} className="rs-list" hidden={!autocomplete.open}>
              {autocomplete.loading ? <li className="rs-loading" role="presentation">불러오는 중…</li> : autocomplete.suggestions.map((name, index) => {
                const match = autocomplete.partial ? name.toLowerCase().indexOf(autocomplete.partial.toLowerCase()) : -1;
                return <li className="rs-option" id={autocomplete.optionId(index)} key={name} role="option" aria-selected={index === autocomplete.activeIndex}
                  onMouseDown={event => event.preventDefault()} onClick={() => autocomplete.select(name)}>
                  <Code2 className="rs-icon" size={14} aria-hidden="true"/><span className="rs-name">{match < 0 ? name : <>{name.slice(0, match)}<strong className="rs-match">{name.slice(match, match + autocomplete.partial.length)}</strong>{name.slice(match + autocomplete.partial.length)}</>}</span>
                </li>;
              })}
            </ul>
          </div>
          <button className="button primary" type="submit" disabled={!repository.restored}>{repository.isScanning ? <LoaderCircle className="spin" size={16}/> : null}{repository.isScanning ? "진행 중인 검사 보기" : "실제 검사 시작"}<ArrowRight size={16}/></button>
        </div>
        {error && <p id="repository-error" className="form-error" role="alert">{error}</p>}
        <p className="sr-only" aria-live="polite" aria-atomic="true">{autocomplete.announcement}</p>
        <p id="repository-hint" className="field-hint">owner/repository 또는 owner.github.io를 입력하세요.<br/>GitHub Pages는 해당 저장소로 변환해 검사합니다.</p>
      </form>
      {mcpInline && <McpConnect embedded/>}
    </section>
    {!mcpInline && <McpConnect/>}
    <section className="home-features" aria-labelledby="home-features-title">
      <div className="home-features-heading">
        <div><p className="eyebrow">FIND. UNDERSTAND. FIX.</p><h2 id="home-features-title">발견에서 수정까지, 한 흐름으로.</h2></div>
        <Link className="text-link" href="/help">검사 범위 알아보기<ArrowRight size={15} aria-hidden="true"/></Link>
      </div>
      <div className="home-feature-grid">
        <article className="home-feature">
          <div className="home-feature-top"><span className="home-feature-icon"><ShieldCheck size={26} strokeWidth={1.6} aria-hidden="true"/></span><span className="home-feature-step" aria-hidden="true">01 / FIND</span></div>
          <h3>엔진으로 발견</h3><p>코드·의존성·비밀정보의<br/>실제 관찰 근거를 확인하세요.</p>
        </article>
        <article className="home-feature">
          <div className="home-feature-top"><span className="home-feature-icon"><Sparkles size={26} strokeWidth={1.6} aria-hidden="true"/></span><span className="home-feature-step" aria-hidden="true">02 / UNDERSTAND</span></div>
          <h3>GPU로 해석</h3><p>연결 가능한 경우 Red–Blue가<br/>위험과 수정 방향을 설명합니다.</p>
        </article>
        <article className="home-feature">
          <div className="home-feature-top"><span className="home-feature-icon"><Unplug size={26} strokeWidth={1.6} aria-hidden="true"/></span><span className="home-feature-step" aria-hidden="true">03 / FIX</span></div>
          <h3>MCP로 전달</h3><p>결과를 코딩 도구에 전달하고<br/>수정 후 다시 검사하세요.</p>
        </article>
      </div>
    </section>
  </main>;
}
