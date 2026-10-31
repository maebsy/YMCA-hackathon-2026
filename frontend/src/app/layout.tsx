import type { Metadata } from "next";
import { IncidentProvider } from "@/components/incident-provider";
import Shell from "@/components/shell";
import { RepositoryProvider } from "@/components/repository-provider";
import "./globals.css";
import "./flow.css";
import "./incident.css";

export const metadata: Metadata = { title: "72hours — 만드는 사람 곁의 보안 가이드", description: "공개 GitHub 저장소를 실제 엔진으로 검사하고, GPU Red–Blue 해석과 MCP로 수정과 재검사를 준비하세요." };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="ko" data-theme="dark" suppressHydrationWarning><body><IncidentProvider><RepositoryProvider><Shell>{children}</Shell></RepositoryProvider></IncidentProvider></body></html>;
}
