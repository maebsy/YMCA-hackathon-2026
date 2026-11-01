"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useSyncExternalStore, type CSSProperties, type FormEvent } from "react";
import { ArrowRight, Code2, LoaderCircle, Pause, Play } from "lucide-react";
import { normalizeRepositoryUrl, useRepository } from "@/components/repository-provider";
import { useRepoAutocomplete } from "@/lib/use-repo-autocomplete";
import { repositoryInputUrl } from "@/lib/repo-suggest";
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
  const previewUrl = normalizeRepositoryUrl(repositoryInputUrl(repository.repoInput));
  function submit(event: FormEvent) {
    event.preventDefault();
    if (repository.isScanning) {
      router.push("/repository");
      return;
    }
    if (!repository.restored) return;
    const url = normalizeRepositoryUrl(repositoryInputUrl(repository.repoInput));
    if (!url) {
      setError("공개 GitHub 저장소 주소를 넣어 주세요. 예: github.com/owner/repo");
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
      <h1><span className="hero-title-line">코드 <span className="hero-security-word">보안</span></span><br/><span className="hero-title-accent">주소 하나면 됩니다.</span></h1>
    </div>
    <section className="entry-panel card" aria-label="GitHub 저장소 점검">
      <div className="entry-panel-top"><label htmlFor="repository">공개 GitHub 저장소</label></div>
      <form onSubmit={submit} noValidate>
        <div className="url-form-row">
          <div className="url-field rs-field"><Code2 size={20} aria-hidden="true"/>
            <input {...autocomplete.inputProps} ref={input} id="repository" name="repository" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" placeholder="github.com/owner/repository 또는 owner.github.io" onChange={event => { autocomplete.inputProps.onChange(event); if (error) setError(""); }} disabled={!repository.restored || repository.isScanning} aria-invalid={!!error} aria-describedby={[error && "repository-error", "repository-hint"].filter(Boolean).join(" ")}/>
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
          <button className="button primary" type="submit" disabled={!repository.restored}>{repository.isScanning ? <LoaderCircle className="spin" size={16}/> : null}{repository.isScanning ? "진행 상황 보기" : "점검하기"}<ArrowRight size={16}/></button>
        </div>
        {error && <p id="repository-error" className="form-error" role="alert">{error}</p>}
        <p className="sr-only" aria-live="polite" aria-atomic="true">{autocomplete.announcement}</p>
        <p id="repository-hint" className="field-hint rs-hint">{previewUrl ? `검사할 저장소: ${previewUrl}` : !repository.repoInput.trim() ? <>github.com/owner/repository 또는 owner.github.io를 입력하세요.<br/>GitHub Pages는 해당 저장소로 변환해 검사합니다.</> : null}</p>
        <p className="sr-only" aria-live="polite" aria-atomic="true">{previewUrl ? `검사할 저장소: ${previewUrl}` : ""}</p>
      </form>
      {mcpInline && <McpConnect embedded/>}
    </section>
    {!mcpInline && <McpConnect/>}
  </main>;
}
