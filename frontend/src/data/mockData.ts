import { Finding, LogItem } from "@/types/security";

export const initialFindings: Finding[] = [
  {
    id: "s1",
    decision: "act",
    decisionLabel: "act · 지금 바로",
    title: "브라우저 코드에 관리자 키(service_role) 노출",
    file: "src/lib/supabase.ts:4 · gitleaks",
    verdict: "수동 확인",
    verdictType: "warn",
    confidence: "확신 high",
    scope: "browser · public",
    fixed: false,
    desc: "누구나 브라우저 개발자 도구(F12)에서 이 관리자 키를 볼 수 있으며, RLS(행 단위 보안)를 모두 무시하고 고객 정보를 읽거나 삭제할 수 있습니다.",
    redScenario:
      "공격자가 번들된 JS 파일에서 'SUPABASE_SERVICE_ROLE_KEY'를 자동 수집 봇으로 추출한 뒤, REST API를 직접 호출해 1초 만에 전체 회원 테이블을 덤프하거나 삭제합니다.",
    why: [
      "공개된 프론트엔드 코드에 드러난 키는 자동 수집 봇이 즉시 찾아 악용합니다",
      "로그인 없이 인터넷에서 누구나 바로 접근할 수 있습니다",
      "전체 계정 권한과 고객 개인정보가 직접 걸려 있습니다",
    ],
    commands: {
      windows:
        "Add-Content -Path .env.local -Value 'SUPABASE_SERVICE_ROLE_KEY=<새로_발급한_키>'\ngit rm --cached .env",
      macos:
        "echo 'SUPABASE_SERVICE_ROLE_KEY=<새로_발급한_키>' >> .env.local\ngit rm --cached .env",
      linux:
        "echo 'SUPABASE_SERVICE_ROLE_KEY=<새로_발급한_키>' >> .env.local\ngit rm --cached .env",
    },
    aiPrompt: `[72hours 보안 수정 지시 | ID: s1 | 규칙: gitleaks-supabase-service-key]
대상 위치: src/lib/supabase.ts (4번째 줄)
조치 지시:
1. 클라이언트 번들(NEXT_PUBLIC_*)에서 service_role 키 참조를 즉시 제거하고 anon 키로 교체하세요.
2. 관리자 권한 작업은 서버 전용 Route Handler(src/app/api/*) 내부에서만 process.env.SUPABASE_SERVICE_ROLE_KEY로 호출하도록 분리하세요.
(주의: 먼저 Supabase 대시보드에서 노출된 기존 키를 폐기하고 재발급해야 합니다.)`,
  },
  {
    id: "s2",
    decision: "attend",
    decisionLabel: "attend · 이번 주",
    title: "주문 조회 API의 SQL 주입 (SQL Injection)",
    file: "src/app/api/orders/route.ts:9 · CWE-89",
    verdict: "Red 통과",
    verdictType: "ok",
    confidence: "확신 high",
    scope: "server · api",
    fixed: false,
    desc: "사용자가 입력한 주문번호 파라미터를 검증 없이 SQL 문자열에 그대로 이어 붙여서 실행하고 있습니다.",
    redScenario:
      "공격자가 orderId 파라미터에 ' OR '1'='1을 주입하여 다른 고객의 전체 주문 내역과 결제 배송지 정보를 무단 열람합니다.",
    why: [
      "외부 입력값이 쿼리문 구조를 직접 변경할 수 있는 경로가 열려 있습니다",
      "파라미터 바인딩(Prepared Statement)으로 고쳐도 기존 기능은 100% 유지됩니다",
    ],
    commands: {
      windows: "npx opengrep scan --rule cwe-89 src/app/api/orders/route.ts",
      macos: "npx opengrep scan --rule cwe-89 src/app/api/orders/route.ts",
      linux: "npx opengrep scan --rule cwe-89 src/app/api/orders/route.ts",
    },
    aiPrompt: `[72hours 보안 수정 지시 | ID: s2 | 규칙: custom-vibe-sql-injection (CWE-89)]
대상 위치: src/app/api/orders/route.ts (9번째 줄)
조치 지시:
템플릿 리터럴(\`SELECT * FROM orders WHERE id = '\${orderId}'\`)로 직접 문자열을 결합한 쿼리를 제거하고, 파라미터 바인딩($1) 또는 Supabase 클라이언트의 .eq('id', orderId) 메서드로 교체하세요.`,
  },
  {
    id: "s3",
    decision: "attend",
    decisionLabel: "attend · 이번 주",
    title: "고객 테이블 RLS(행 단위 보안) 꺼짐",
    file: "supabase/migrations/20261001_init.sql · 자체 검사기",
    verdict: "Red 통과",
    verdictType: "ok",
    confidence: "확신 high",
    scope: "database · public",
    fixed: false,
    desc: "바이브코딩 중 자주 누락되는 설정입니다. 테이블을 만들었지만 RLS가 활성화되지 않아 anon 키만으로도 전체 고객 행을 조회할 수 있습니다.",
    redScenario:
      "프론트엔드에 공개된 기본 anon 키로 Supabase API에 직접 GET 요청을 보내면 본인이 아닌 타인의 회원 정보까지 모두 반환됩니다.",
    why: [
      "Supabase public 스키마 테이블은 RLS를 켜지 않으면 기본적으로 전체 공개됩니다",
      "자체 Python 설정 검사기에서 ALTER TABLE ... ENABLE ROW LEVEL SECURITY 누락이 확인되었습니다",
    ],
    commands: {
      windows:
        "npx supabase migration new enable_rls_customers\nnpx supabase db push",
      macos:
        "npx supabase migration new enable_rls_customers && npx supabase db push",
      linux:
        "npx supabase migration new enable_rls_customers && npx supabase db push",
    },
    aiPrompt: `[72hours 보안 수정 지시 | ID: s3 | 규칙: vibe-supabase-rls-missing]
대상 위치: supabase/migrations/20261001_init.sql
조치 지시:
customers 테이블에 'ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;'를 추가하고, auth.uid() = user_id 조건의 SELECT/UPDATE 정책(Policy) 마이그레이션 파일을 생성하세요.`,
  },
  {
    id: "s4",
    decision: "attend",
    decisionLabel: "attend · 이번 주",
    title: "next 15.1.0 · 미들웨어 권한 우회 취약점 (EPSS 99%)",
    file: "package-lock.json · CVE-2025-29927",
    verdict: "Red 통과",
    verdictType: "ok",
    confidence: "확신 high",
    scope: "dependency · osv",
    fixed: false,
    desc: "현재 사용 중인 Next.js 버전에 알려진 심각한 보안 취약점이 있어 특정 헤더 조작만으로 인증 미들웨어를 건너뛸 수 있습니다.",
    redScenario:
      "공격자가 요청 헤더에 조작된 내부 미들웨어 서브요청 값을 넣어 관리자 전용 페이지(/admin)를 로그인 없이 통과합니다.",
    why: [
      "실제 악용 확률(EPSS)이 99%로 인터넷에 공개 공격 코드가 돌아다니고 있습니다",
      "패치 버전 업그레이드 한 줄로 안전하게 해결됩니다",
    ],
    commands: {
      windows: "npm install next@latest\nnpm audit fix",
      macos: "npm install next@latest && npm audit fix",
      linux: "npm install next@latest && npm audit fix",
    },
    aiPrompt: `[72hours 보안 수정 지시 | ID: s4 | 규칙: osv-CVE-2025-29927]
대상 위치: package.json / package-lock.json
조치 지시:
CVE-2025-29927 취약점이 패치된 최신 안정 버전으로 next 패키지를 업데이트하고 빌드 호환성을 확인하세요.`,
  },
  {
    id: "s5",
    decision: "trackstar",
    decisionLabel: "track* · 지켜보기",
    title: "후기 본문 HTML 그대로 출력 (DOM XSS)",
    file: "src/components/ReviewCard.tsx:14 · opengrep",
    verdict: "Red 통과",
    verdictType: "ok",
    confidence: "확신 medium",
    scope: "browser · component",
    fixed: false,
    desc: "고객이 작성한 카페 후기 내용을 정제(Sanitize)하지 않고 dangerouslySetInnerHTML로 화면에 바로 그리고 있습니다.",
    redScenario:
      "악성 스크립트가 담긴 후기를 등록하면, 해당 후기를 보는 다른 방문자의 브라우저에서 세션 쿠키 탈취 스크립트가 실행됩니다.",
    why: [
      "현재 텍스트만 입력받도록 되어 있으나 API로 HTML 태그를 직접 넣으면 실행됩니다",
      "일반 JSX 텍스트 바인딩으로 바꾸면 즉시 차단됩니다",
    ],
    commands: {
      windows: "npm install dompurify @types/dompurify",
      macos: "npm install dompurify @types/dompurify",
      linux: "npm install dompurify @types/dompurify",
    },
    aiPrompt: `[72hours 보안 수정 지시 | ID: s5 | 규칙: react-dangerously-set-inner-html]
대상 위치: src/components/ReviewCard.tsx (14번째 줄)
조치 지시:
dangerouslySetInnerHTML 속성을 제거하고 일반 JSX 중괄호({review.content}) 렌더링으로 변경하거나 DOMPurify.sanitize()를 거치도록 수정하세요.`,
  },
];

export const defaultLogs: LogItem[] = [
  { time: "05:42:03", step: "clone   ", msg: "minji-cafe/order-site @ 3f9c2e1", status: "✓", type: "ok" },
  { time: "05:42:09", step: "osv     ", msg: "외부 부품 검사 · package-lock.json", status: "✓ 4건 (묶음 1건)", type: "ok" },
  { time: "05:42:15", step: "opengrep", msg: "코드 검사 · 자체 바이브코딩 규칙 21개 + Aikido MIT", status: "✓ 3건", type: "ok" },
  { time: "05:42:16", step: "gitleaks", msg: "비밀키 유출 검사 (src/lib/supabase.ts)", status: "! 1건 (act)", type: "warn" },
  { time: "05:42:17", step: "cleanup ", msg: "수집된 원본 소스 코드 완전 삭제 (Zero-Retention)", status: "✓", type: "ok" },
  { time: "05:42:18", step: "gpu-llm ", msg: "로컬 L4 GPU Red–Blue 검증 루프 완료 (5건 해석 완료)", status: "✓ Ready", type: "ok" },
];

export const mockApiPayloads = {
  poll: {
    status: 202,
    scan_id: 41,
    queued_job_ids: ["job_s1", "job_s2", "job_s3", "job_s4", "job_s5"],
    poll_after_seconds: 3,
  },
  explain: {
    scan_id: 41,
    unscanned_count: 0,
    results: [
      {
        id: "s1",
        risk: { decision: "act", score: 98, factors: [{ reason: "공개 번들 내 service_role 키 노출" }] },
        red_verdict: "manual_review",
        needs_manual_review: true,
        guide: { actions: [{ os: "windows", lines: ["Add-Content -Path .env.local ..."] }] },
      },
    ],
  },
  report: {
    report_type: "plain_completion_72h",
    elapsed_hours: 10.78,
    unscanned_areas: 0,
    sections: ["발견 일시·경로", "원인", "영향 범위", "조치 내용", "검증 결과"],
  },
};
