import type { Metadata } from "next";
import { DemoProvider } from "@/components/demo-provider";
import Shell from "@/components/shell";
import { RepositoryProvider } from "@/components/repository-provider";
import "./globals.css";
import "./flow.css";

export const metadata: Metadata = { title: "72hours — 만드는 사람 곁의 보안 가이드", description: "URL로 시작하는 샘플 체험과 GitHub 저장소 실제 검사. 근거를 이해하고 다음 조치를 준비하세요." };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="ko" data-theme="dark" suppressHydrationWarning><body><DemoProvider><RepositoryProvider><Shell>{children}</Shell></RepositoryProvider></DemoProvider></body></html>;
}
