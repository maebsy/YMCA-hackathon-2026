"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, CircleHelp } from "lucide-react";
import IncidentWorkspace from "./incident-workspace";

type View = "incident" | "help";
const titles: Record<View, [string, string, string]> = {
  incident: ["INCIDENT · REPORTING SUPPORT", "확인한 사실부터, 신고 준비까지.", "필요한 사실만 답하면 신고 대상·기한과 두 신고서 초안을 함께 만듭니다. 이후 비어 있는 칸만 이어서 묻습니다."],
  help: ["HELP & SCOPE", "한 장으로 보는 서비스 흐름", "저장소 검사부터 실제검증, MCP 전달, 24·72시간 사고 신고까지 어떻게 이어지는지 먼저 보세요."],
};
// 도움말 첫 화면의 서비스 흐름 그림. 각 단계는 실제 화면으로 이어집니다
const flow: { step: string; title: string; text: string; href: string; note?: string }[] = [
  { step: "1", title: "저장소 입력", text: "공개 GitHub 주소 하나", href: "/" },
  { step: "2", title: "보안엔진 검사", text: "코드·부품·비밀키·설정 4종", href: "/repository" },
  { step: "3", title: "AI 쉬운 설명", text: "GPU Red–Blue가 위험·수정 방법 설명", href: "/repository" },
  { step: "4", title: "결과·리포트", text: "3줄 요약과 수정 지시문", href: "/report", note: "여기서 갈라져요" },
];
const branches: { title: string; text: string; href: string; label: string }[] = [
  { title: "실제검증", text: "고친 코드를 격리 환경에서 실제로 공격해 막히는지 확인", href: "/verify", label: "Red–Blue" },
  { title: "MCP로 전달", text: "수정 지시를 Cursor·Claude Code 같은 AI 코딩 도구로 바로 보냄", href: "/mcp-guide", label: "MCP" },
  { title: "사고 신고", text: "사고가 의심되면 검사 기록으로 24시간·72시간 신고서 초안", href: "/incident", label: "24h · 72h" },
];

function FlowDiagram() {
  return <article className="card help-flow" aria-labelledby="help-flow-title">
    <h2 id="help-flow-title">72hours는 이렇게 이어집니다</h2>
    <ol className="help-flow-main">{flow.map((node, index) => <li key={node.step}>
      <Link href={node.href}><span className="help-flow-step">{node.step}</span><strong>{node.title}</strong><small>{node.text}</small>{node.note && <span className="help-flow-branch-note">{node.note}</span>}</Link>
      {index < flow.length - 1 && <ArrowRight className="help-flow-arrow" size={18} aria-hidden="true"/>}
    </li>)}</ol>
    <p className="help-flow-fork" aria-hidden="true">결과에서 필요한 것으로 이어서</p>
    <ul className="help-flow-branches">{branches.map(branch => <li key={branch.title}>
      <Link href={branch.href}><span className="help-flow-label">{branch.label}</span><strong>{branch.title}</strong><small>{branch.text}</small></Link>
    </li>)}</ul>
    <p className="muted help-flow-note">고친 뒤에는 같은 저장소를 다시 검사하면 해결된 항목이 ‘해결 확인’으로 바뀝니다. 각 상자를 누르면 그 화면으로 갑니다.</p>
  </article>;
}

function Help() {
  return <section className="help-content">
      <FlowDiagram/>
      <details className="card help-more">
        <summary><h2>단계별 자세한 설명과 검사 범위</h2><span className="muted">눌러서 펼치기</span></summary>
      <article>
        <CircleHelp size={24} className="accent"/><h2>GitHub 주소로 시작하고, 한 단계씩.</h2>
        <ol className="repair-steps">
          <li><span>1</span><div><h3>공개 GitHub 저장소 입력</h3><p>홈에서 https://github.com/owner/repository 형식의 저장소 루트 주소를 입력하세요. 파일 경로, 로그인 정보, 쿼리와 해시가 있는 주소는 받지 않습니다. 실행하면 저장소 주소를 검사 서버로 보냅니다.</p></div></li>
          <li><span>2</span><div><h3>엔진 검사와 추가 AI 해석</h3><p>실제 검사 화면에서 진행 로그와 도구별 실행 범위를 확인하세요. GPU 해석 서버를 사용할 수 있으면 상위 발견 항목에 Red–Blue 해석을 더합니다. 추가 해석이 실패해도 엔진 결과는 유지합니다.</p></div></li>
          <li><span>3</span><div><h3>근거 확인과 수정</h3><p>발견 항목을 선택하면 관찰 근거와 수정 안내를 볼 수 있습니다. 직접 조치한 항목은 ‘재검증 대기’로 표시하고, 같은 저장소를 다시 검사해 이전 결과와 비교하세요.</p></div></li>
          <li><span>4</span><div><h3>MCP 전달과 리포트</h3><p>검사 결과를 파일로 저장하고 MCP 설정을 복사해 AI 코딩 도구에 연결할 수 있습니다. 전달 가능 건수와 차단 사유를 확인하세요. 실제 검사 데이터로 HTML 리포트와 Markdown 문서도 만듭니다.</p></div></li>
          <li><span>5</span><div><h3>사고가 의심되면 신고 준비</h3><p>사고 사실을 기록하고 침해사고·개인정보 유출 신고의 대상과 기한을 각각 확인하세요. 공통 사실로 두 신고서 초안을 만들고 보완할 항목과 공식 제출처를 확인합니다. 저장소 검사 없이도 시작할 수 있습니다.</p></div></li>
        </ol>
      </article>
      <article>
        <h2>검사 범위와 결과 보관</h2>
        <p><Link className="text-link" href="/repository">검사 결과와 진행 상황 보기 <ArrowRight size={14}/></Link></p>
        <dl className="help-definitions">
          <div><dt>검사 대상과 접근 권한</dt><dd>공개 GitHub 저장소를 검사합니다. 서버 설정에 따라 로그인과 허용된 저장소 소유자 권한이 필요할 수 있습니다. 접근이 거절되면 로그인 상태와 해당 저장소의 검사 허용 여부를 확인하세요. 일반 웹사이트 주소만으로 서버 코드나 DB를 검사하지 않습니다.</dd></div>
          <div><dt>엔진 결과와 추가 해석</dt><dd>도구가 실제로 실행한 범위와 관찰 근거를 먼저 확인하세요. AI 해석이나 발견 항목이 없다는 사실만으로 서비스 전체가 안전하다고 판단할 수 없습니다. 추가 AI 해석을 사용할 수 없어도 엔진 결과와 기본 안내는 남습니다.</dd></div>
          <div><dt>브라우저에 남는 결과</dt><dd>마지막 검사 결과와 수동 조치 표시를 이 브라우저에 저장해 새로고침 후 복원합니다. 다른 저장소를 입력해도 새 검사가 완료되기 전에는 이전 결과를 유지하므로 결과에 표시된 저장소를 확인하세요. 브라우저 저장소를 지우면 복원할 수 없습니다.</dd></div>
          <div><dt>MCP 파일과 설정</dt><dd>지원하는 브라우저에서는 자동 저장을 켤 수 있습니다. 지원하지 않으면 결과 파일을 내려받아 같은 이름으로 저장하세요. 설정의 사용자 경로와 설치 위치를 확인한 뒤 AI 코딩 도구에 연결하고, 전달 가능 항목과 제한을 검토하세요.</dd></div>
          <div><dt>사고 기록과 신고서 초안</dt><dd>신고 대상 확인이나 문서 생성을 누르면 입력한 사고 정보를 서버로 보냅니다. 선택한 검사 발견은 원인 후보이며 실제 침해나 유출을 확정하지 않습니다. 사고 기록과 편집 문서는 화면 이동 동안 유지되며 새로고침하면 사라집니다. 입력을 바꾸면 이전 안내와 문서에 갱신이 필요하다고 표시합니다.</dd></div>
          <div><dt>신고·통지와 기한</dt><dd>기관 신고와 정보주체 통지는 별도입니다. 통지 의무와 유출 가능성 통지는 현재 자동 판정 범위에 포함되지 않습니다. 초안의 법령·제재 안내와 최신 서식은 공식 기관에서 확인하세요. 문서 생성·다운로드는 기관 접수나 통지 완료를 뜻하지 않습니다. 신고 기한은 사고 인지 시각 기준이며 검사 후 수정에 걸린 시간과 구분합니다.</dd></div>
        </dl>
      </article>
      </details>
  </section>;
}

export default function Workspace({ view }: { view: View }) {
  const [eyebrow, title, description] = titles[view];
  return <main id="main" className="workspace container" tabIndex={-1}>
    <Link className="back-link" href={view === "incident" ? "/repository" : "/"}><ArrowLeft size={14}/>{view === "incident" ? "검사 결과로" : "저장소 입력으로"}</Link>
    <div className="workspace-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
    {view === "incident" ? <IncidentWorkspace/> : <Help/>}
  </main>;
}
