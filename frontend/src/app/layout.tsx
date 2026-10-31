import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "72hours · YMCA 潑墨(발묵) 보안 아키텍처 | 찾고, 고치고, 72시간 안에 끝냅니다.",
  description:
    "화선지에 스미는 맑은 먹빛처럼 보안의 해법을 번지게 하다. Opengrep·OSV·Gitleaks 및 자체 특화 룰셋으로 진단하고, 로컬 GPU LLM의 Red–Blue 검증 루프를 통과한 안전한 수정 지시만 코딩툴(MCP)로 전달합니다.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Noto+Serif+KR:wght@400;600;700;900&display=swap"
          rel="stylesheet"
        />
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
        />
      </head>
      <body className="antialiased selection:bg-[#1F4E43] selection:text-[#FFFEFA]">
        {children}
      </body>
    </html>
  );
}
