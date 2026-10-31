import type { Metadata } from "next";
import Link from "next/link";
import VerifyPanel from "@/components/verify-panel";
import "./verify.css";

export const metadata: Metadata = { title: "Red–Blue 실검증 — 72hours", description: "수정 전에는 공격이 통하고 수정 후에는 막히는지, 기능은 그대로인지 실제로 실행해 확인합니다." };

export default function Page() {
  return <main id="main" className="vp-page" tabIndex={-1}>
    <Link className="vp-back" href="/">← 저장소 검사로</Link>
    <div className="vp-heading">
      <p className="vp-eyebrow">RED–BLUE · VERIFY</p>
      <h1>고쳤다는 말 대신, 실제로 공격해 봅니다.</h1>
      <p>AI가 낸 수정이 정말 통하는지 격리 환경에서 수정 전·후를 직접 실행해 비교합니다. 지금은 우리 데모 과녁으로만 실행합니다.</p>
    </div>
    <VerifyPanel/>
  </main>;
}
