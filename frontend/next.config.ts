import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    const backend = (process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
  // 검사(/api/scans)는 clone·스캐너 실행으로 수십 초~수 분 걸립니다. 기본 프록시 제한(30초)을 10분으로 늘립니다
  experimental: { proxyTimeout: 600_000 },
  // Docker 배포 빌드만 standalone. 기존 npm run build/start 실행 방식은 유지합니다.
  output: process.env.NEXT_STANDALONE === "true" ? "standalone" : undefined,
};

export default nextConfig;
