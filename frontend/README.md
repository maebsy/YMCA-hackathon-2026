# 72hours 프론트엔드 프로토타입

로그인·스캔·재검사·GPU 상태·공격 재현·리포트는 데모 데이터입니다. 실제 인증이나 보안 검증을 수행하지 않으며, 예제 리포트를 실제 조치 증빙으로 사용할 수 없습니다.

Node.js와 npm을 설치한 뒤 이 디렉터리에서 `npm ci`를 먼저 실행하세요. `npm run lint`와 `npm run build`로 검증할 수 있습니다.

Tailwind CSS는 설치된 `@tailwindcss/turbopack` 로더로 빌드합니다. 브라우저의 Tailwind CDN 스크립트를 사용하지 않습니다. Google Fonts 연결 실패 시 시스템 폰트를 사용합니다.

신고서 입력은 탭 전환 동안 유지되며, 페이지 새로고침 시 초기화됩니다.

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
