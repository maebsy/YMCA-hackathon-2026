import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "72hours — 바이브 코더 보안 플랫폼 | 찾고, 고치고, 72시간 안에 끝냅니다.",
  description:
    "바이브코더와 비개발자도 즉시 다음 행동이 보이는 웹사이트 보안 서비스. Opengrep·OSV·Gitleaks 및 자체 특화 룰셋으로 진단하고, 로컬 GPU LLM의 Red–Blue 검증 루프를 통과한 안전한 수정 지시만 코딩툴(MCP)로 전달합니다.",
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
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&display=swap"
          rel="stylesheet"
        />
        {/* Tailwind CDN 로드 (temp 원본과 100% 동일한 유틸리티 렌더링 보장) */}
        <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body className="min-h-screen bg-[#0a0a0a] text-[#fafafa] selection:bg-[#d4ff3a] selection:text-black antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
