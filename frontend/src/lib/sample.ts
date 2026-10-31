export const SAMPLE_SITE = "https://tiny-shop.example";
export const SAMPLE_REPO = "72hours-demo/tiny-shop";
export type Priority = "긴급" | "높음" | "보통";
export type Finding = {
  id: string; title: string; priority: Priority; category: string; location: string;
  observation: string; impact: string; evidence: string; steps: string[]; verify: string;
};

export const findings: Finding[] = [
  {
    id: "SEC-001", title: "공개 번들에 포함된 서비스 키", priority: "긴급", category: "비밀정보", location: "/assets/app.js · 브라우저 번들",
    observation: "가상 서비스의 공개 JavaScript에 관리자 권한용 키가 포함된 상황을 가정한 예시입니다.",
    impact: "관리자 키가 브라우저로 전달되면 의도한 데이터 접근 경계를 우회하는 데 사용될 수 있습니다. 키의 실제 권한과 노출 범위는 별도 확인해야 합니다.",
    evidence: "// 가상 번들 예시 · 실제 키가 아닙니다\nconst serviceRoleKey = 'DEMO_PLACEHOLDER_ONLY';",
    steps: ["키의 권한과 노출 범위를 확인하고, 노출된 키는 제공자 콘솔에서 폐기·교체하세요.", "관리자 권한을 사용하는 코드를 서버 전용 경로로 옮기고 브라우저 번들에서 키를 제거하세요.", "공개 클라이언트에는 최소 권한만 제공하고, 새 빌드와 과거 배포 파일의 노출 여부를 검토하세요."],
    verify: "새 브라우저 번들에서 키가 제거됐는지, 이전 키의 사용이 거부되는지, 필요한 정상 기능이 동작하는지 확인하세요.",
  },
  {
    id: "SEC-002", title: "콘텐츠 보안 정책(CSP) 누락", priority: "높음", category: "보안 헤더", location: "GET / · 응답 헤더",
    observation: "샘플 HTTP 응답에 Content-Security-Policy 헤더가 없는 상황입니다.",
    impact: "스크립트 삽입 문제가 생겼을 때 브라우저의 추가 방어가 제한될 수 있습니다. 헤더 누락만으로 침해나 XSS 취약점이 입증되지는 않습니다.",
    evidence: "HTTP/2 200\ncontent-type: text/html\n// 샘플: Content-Security-Policy 헤더 없음",
    steps: ["앱이 사용하는 스크립트, 스타일과 외부 리소스 출처를 정리하세요.", "Content-Security-Policy-Report-Only로 정상 기능과 위반 보고를 먼저 확인하세요.", "nonce 또는 해시 기반 정책을 검토하고, 검증한 정책을 실제 응답에 적용하세요."],
    verify: "배포 응답의 CSP와 위반 보고를 확인하고, 로그인·결제 등 정상 동작을 회귀 테스트하세요.",
  },
  {
    id: "SEC-003", title: "HTTPS 강제 정책(HSTS) 누락", priority: "높음", category: "보안 헤더", location: "GET / · HTTPS 응답",
    observation: "샘플 HTTPS 응답에 Strict-Transport-Security 헤더가 없는 상황입니다.",
    impact: "브라우저가 이후 접속에서 HTTPS 사용을 강제하도록 하는 정책이 없습니다. HTTPS 지원 여부와 리다이렉트 설정을 함께 확인해야 합니다.",
    evidence: "HTTP/2 200\n// 샘플: Strict-Transport-Security 헤더 없음",
    steps: ["HTTPS 인증서와 HTTP → HTTPS 리다이렉트가 올바르게 동작하는지 확인하세요.", "짧은 max-age부터 HSTS 정책을 적용하고 실제 응답을 확인하세요.", "모든 하위 도메인의 HTTPS 준비를 확인한 뒤 includeSubDomains를 검토하세요. preload는 별도 요건을 확인하세요."],
    verify: "HTTPS 응답의 HSTS 값과 HTTP 리다이렉트, 관련 하위 도메인에 접속 문제가 없는지 확인하세요.",
  },
  {
    id: "SEC-004", title: "세션 쿠키의 Secure 속성 누락", priority: "보통", category: "세션", location: "POST /login · Set-Cookie 예시",
    observation: "가상 로그인 응답의 세션 쿠키에 Secure 속성이 없는 예시입니다. 실제 로그인이나 인증 요청은 하지 않습니다.",
    impact: "쿠키의 HTTPS 전용 전송을 보장하지 못할 수 있습니다. 실제 서비스의 쿠키 발급 경로와 배포 설정을 함께 확인해야 합니다.",
    evidence: "// 가상 응답 · 실제 세션이 아닙니다\nSet-Cookie: session=DEMO_ONLY; HttpOnly; SameSite=Lax",
    steps: ["프로덕션의 HTTPS와 세션 쿠키 발급 경로를 확인하세요.", "세션 쿠키에 Secure를 적용하고 HttpOnly, SameSite와 만료 정책을 함께 검토하세요.", "개발 환경과 프로덕션 설정을 구분하고 로그인·로그아웃 흐름을 테스트하세요."],
    verify: "실제 배포 환경의 Set-Cookie 속성과 HTTPS 로그인, 세션 만료·종료를 확인하세요.",
  },
];

export function validateWebsite(value: string): string | null {
  const raw = value.trim();
  if (!raw || raw.length > 2048 || /[\s\u0000-\u001f\u007f\\?#]/.test(raw)) return null;
  if (raw.includes(":") && !/^https?:\/\//i.test(raw)) return null;
  try {
    const candidate = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const structure = candidate.match(/^https?:\/\/([^/]+)(\/.*)?$/i);
    if (!structure || /[@%]/.test(structure[1])) return null;
    const url = new URL(candidate);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null;
    const host = url.hostname.toLowerCase();
    const labels = host.split(".");
    if (host.length > 253 || labels.length < 2 || labels.some(label => !/^[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?$/i.test(label))) return null;
    if (!/^(?:[a-z]{2,63}|xn--[a-z\d-]+)$/i.test(labels.at(-1)!) || /\.(?:localhost|local|internal)$/i.test(host)) return null;
    return url.href;
  } catch { return null; }
}

export function repairRequest(finding: Finding) {
  return [
    `[72hours 고정 샘플 수정 요청 · ${SAMPLE_SITE}]`,
    `예제 저장소: ${SAMPLE_REPO} (가상)`,
    "이 내용은 실제 사용자 사이트의 검사 결과가 아닙니다. 내 프로젝트에 해당하는지 먼저 확인해 주세요.",
    `\n검토 항목: ${finding.title}`, `샘플 관찰 위치: ${finding.location}`, `관찰: ${finding.observation}`,
    "\n수정 전에 실제 파일·설정·권한을 확인하고, 적용할 변경과 영향을 설명해 주세요. 키나 개인정보를 요청하거나 출력하지 마세요.",
    ...finding.steps.map((step, i) => `${i + 1}. ${step}`),
    `\n수정 후 확인: ${finding.verify}`,
    "변경한 파일과 검증 결과, 아직 확인하지 못한 점을 알려 주세요. 실제 검증 없이 해결 또는 안전하다고 단정하지 마세요.",
  ].join("\n");
}

export function reportMarkdown(marked: string[], context: string) {
  const pending = findings.filter(f => marked.includes(f.id)).length;
  return [
    "# 72hours 샘플 보안 리포트", `\n샘플 사이트: ${SAMPLE_SITE} (가상)`, `예제 저장소: ${SAMPLE_REPO} (가상)`,
    `입력 컨텍스트: ${context || "미입력 · 샘플 바로 보기"}`,
    "입력한 URL을 분석한 결과가 아닙니다. 고정 샘플이며 실제 검사·재검증을 수행하지 않았습니다.",
    `\n총 ${findings.length}건 · 미조치 ${findings.length - pending}건 · 재검증 대기 ${pending}건 · 검증 완료 0건`,
    ...findings.map(f => `\n## ${f.id} · ${f.priority} · ${f.title}\n상태: ${marked.includes(f.id) ? "재검증 대기 (사용자 표시)" : "미조치"}\n위치: ${f.location}\n관찰: ${f.observation}\n영향: ${f.impact}\n\n${f.steps.map((s, i) => `${i + 1}. ${s}`).join("\n")}\n\n재검증: ${f.verify}`),
    "\n자동 수정·실제 스캔·신고 전송은 연결되어 있지 않습니다. 무결점 또는 안전함을 보증하지 않습니다.",
  ].join("\n");
}
