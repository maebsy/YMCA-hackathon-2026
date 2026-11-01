"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import IncidentWorkspace from "@/components/incident-workspace";
import { useRepository } from "@/components/repository-provider";

export default function Page() {
  const { result } = useRepository();
  return <main id="main" className="workspace container" tabIndex={-1}>
    <Link className="back-link" href={result ? "/report" : "/"}><ArrowLeft size={14}/>{result ? "검사 결과로" : "저장소 입력으로"}</Link>
    <div className="workspace-heading"><p className="eyebrow">INCIDENT · REPORTING SUPPORT</p><h1>확인한 사실부터, 신고 준비까지.</h1><p>필요한 사실만 답하면 신고 대상·기한과 두 신고서 초안을 함께 만듭니다. 이후 비어 있는 칸만 이어서 묻습니다.</p></div>
    <IncidentWorkspace/>
  </main>;
}
