"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRepository } from "@/components/repository-provider";

// 모든 화면 위에 '지금 서비스의 어느 단계인지'와 다음에 갈 수 있는 곳을 보여 줍니다 (최종 멘토링 피드백)
const MAIN = [
  { path: "/", label: "저장소 입력" },
  { path: "/repository", label: "검사·AI 해석" },
  { path: "/report", label: "결과·리포트" },
] as const;
const NEXT = [
  { path: "/verify", label: "실검증" },
  { path: "/incident", label: "사고 신고 24h·72h" },
] as const;
const SHOWN = new Set<string>([...MAIN.map(step => step.path), ...NEXT.map(step => step.path)]);

export default function JourneyBar() {
  const pathname = usePathname();
  const repository = useRepository();
  if (!SHOWN.has(pathname)) return null;
  const hasResult = !!repository.result;
  const current = MAIN.findIndex(step => step.path === pathname);
  // 결과가 있으면 결과 화면까지는 지난 단계로 봅니다. 검사 중이면 2단계가 진행 중입니다
  // 실검증·사고 신고 화면에서는 검사 결과가 있을 때만 앞 단계를 지난 것으로 봅니다
  const reached = current >= 0 ? current : hasResult ? 3 : 0;
  function state(index: number) {
    if (index === current) return "current";
    if (index < reached || (hasResult && index <= 2)) return "done";
    if (index === 1 && repository.isScanning) return "active";
    return "todo";
  }
  return <nav className="journey-bar container" aria-label="서비스 진행 단계">
    <ol>
      {MAIN.map((step, index) => {
        const s = state(index);
        const reachable = step.path === "/" || (step.path === "/repository" && (hasResult || repository.isScanning)) || (step.path === "/report" && hasResult);
        const content = <><span className="journey-index">{index + 1}</span>{step.label}</>;
        return <li key={step.path} data-state={s} aria-current={s === "current" ? "step" : undefined}>
          {reachable && s !== "current" ? <Link href={step.path}>{content}</Link> : <span>{content}</span>}
        </li>;
      })}
      <li className="journey-split" aria-hidden="true">→</li>
      {NEXT.map(step => {
        const isCurrent = pathname === step.path;
        return <li key={step.path} data-state={isCurrent ? "current" : "branch"} aria-current={isCurrent ? "step" : undefined}>
          {isCurrent ? <span>{step.label}</span> : <Link href={step.path}>{step.label}</Link>}
        </li>;
      })}
    </ol>
  </nav>;
}
