"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import ProgressH from "@/components/progress/scan-progress";
import "@/components/progress/scan-progress.css";
import { useRepository } from "@/components/repository-provider";
import { REPOSITORY_RESULT_PATH } from "@/lib/repository-routes";

export default function RepositoryWorkspace() {
  const repository = useRepository();
  const router = useRouter();
  const sawScan = useRef(false);
  const { isScanning, resultReady, consumeResultReady } = repository;
  useEffect(() => {
    if (isScanning) sawScan.current = true;
    if (resultReady) {
      consumeResultReady();
      if (sawScan.current) router.replace(REPOSITORY_RESULT_PATH);
      sawScan.current = false;
    }
  }, [isScanning, resultReady, consumeResultReady, router]);
  const verified = repository.findings.filter(finding => finding.fixed).length;
  const progressRepo = repository.phase === "done" || repository.reportError ? repository.resultRepo : repository.repoInput;
  const showProgress = repository.phase !== "idle";
  return <main id="main" className="workspace container repository-page" tabIndex={-1}>
    <div className="repository-progress-heading"><h1 className="repository-small-title">저장소 검사</h1><p>결과가 준비되면 자동으로 결과 화면으로 이동합니다.</p><p>저장소 주소가 검사 서버로 전송되며 서버의 로그인·접근 정책이 적용됩니다. 공개 저장소만 입력하세요.</p></div>
    {showProgress && <ProgressH key={repository.startedAt ?? repository.resultRepo} repo={progressRepo.replace(/^https:\/\//, "")} phase={repository.phase} startedAt={repository.startedAt}
      logs={repository.logs.map(log => `[${log.time}] ${log.step} · ${log.msg} · ${log.status}`)} explained={repository.explained}
      counts={repository.result && ["done", "explaining", "reporting"].includes(repository.phase) ? { total: repository.findings.length, open: repository.findings.length - verified } : undefined}
      busy={repository.isScanning} error={repository.reportError || repository.error} reportFailed={!!repository.reportError}
      resultHref={repository.result ? REPOSITORY_RESULT_PATH : undefined}
      onRetry={() => { if (repository.reportError) void repository.prepareReport(true); else void repository.runScan(progressRepo); }}/>
    }
    {repository.phase === "done" && repository.result && <div className="repository-progress-result-action">
      <Link className="button primary" href={REPOSITORY_RESULT_PATH}>결과 보기 <ArrowRight size={16} aria-hidden="true"/></Link>
    </div>}
    {repository.restored && !repository.result && repository.phase === "idle" && <p className="field-hint">홈에서 검사할 GitHub 주소를 입력하세요. <Link className="text-link" href="/">홈으로 가기<ArrowRight size={14}/></Link></p>}
    {!showProgress && repository.error && <p className="form-error" role="alert">{repository.error}</p>}
  </main>;
}
