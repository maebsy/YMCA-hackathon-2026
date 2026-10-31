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
  // Docker 배포 빌드만 standalone. 기존 npm run build/start 실행 방식은 유지합니다.
  output: process.env.NEXT_STANDALONE === "true" ? "standalone" : undefined,
};

export default nextConfig;
