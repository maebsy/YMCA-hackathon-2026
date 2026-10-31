# 시연용 취약 앱 후보: 꽃담 플라워

시연·영상·GPU 효과 실험은 모두 **검사할 데모 저장소**가 있어야 시작할 수 있습니다(결정 필요 ⑥). 팀원 공개 저장소에 아직 데모 앱이 없어서 후보를 하나 만들어 두었습니다. 쓸지 말지는 장양환·유영민이 정합니다.

- 설정: 기획안 데모 시나리오의 "1인 꽃집 사장님". AI 코딩툴로 만든 Next.js + Supabase 주문 페이지
- 위치: 김건우(`papawolf42`) PC의 `C:\Users\alsgu\Dev\ymca-demo-flowershop` (로컬 git 저장소, **아직 GitHub에 없음**)
- `npm ci && npm run build`가 통과합니다. DB 없이도 화면은 열립니다
- `.env`의 키는 모두 가짜입니다. 실제 Supabase 프로젝트와 연결되지 않습니다

## 실측 검사 결과

2026-10-31, Windows, 보안엔진 main(`2de3a09`), 스캐너는 `scripts/security/install-test-tools.py`의 고정 버전.

| 검사 | 결과 |
|---|---|
| 첫 검사 | **열린 문제 26건** (critical 4, high 11, medium 7, low 4), 10.4초 |
| 도구별 | OSV 9건, Opengrep 10건, Gitleaks 2건, 설정 검사 5건 |
| SQL 인젝션 한 줄 고친 뒤 재검사 | 새로 0 / 계속 25 / **해결 1**, 4.8초 |
| LLM 입력 꾸러미 | 26건 (백엔드가 의존성을 패키지별로 묶으므로 실제 해석 건수는 더 적음) |

## 정답셋

**이 표는 데모 저장소 안에 넣지 않습니다.** AI 코딩툴이 정답을 읽으면 GPU 효과 실험의 조치 성공률이 오염됩니다.

| 위험도 | 규칙 | 파일 | 무엇이 문제인가 | 올바른 수정 |
|---|---|---|---|---|
| critical | `sql-string-concat` | `app/api/orders/search/route.ts` | 전화번호를 SQL 문자열에 이어 붙임 | `db.query("... WHERE phone = $1", [phone])` |
| critical | `stripe-webhook-without-signature` | `app/api/webhook/route.ts` | 결제 완료 알림을 서명 확인 없이 믿음 | `stripe.webhooks.constructEvent(본문, stripe-signature 헤더, 웹훅 비밀키)` |
| critical | `supabase-service-role-in-client` | `app/page.tsx` | 브라우저 코드가 service_role 키로 DB에 접속 | anon 키로 바꾸고, 주문 목록 조회는 서버로 옮김 |
| critical | `public-env-exposes-secret` | `app/page.tsx` | `NEXT_PUBLIC_` 이름 때문에 service_role 키가 브라우저 번들에 들어감 | `NEXT_PUBLIC_` 빼고 서버에서만 사용, 키 재발급 |
| high | `jwt-hardcoded-secret` | `app/api/admin/login/route.ts` | JWT 서명 키가 `"flower-secret"` 고정 문자열 | `process.env.JWT_SECRET` |
| high | `nextjs-api-mutation-without-auth` | `app/api/orders/route.ts` | 로그인 확인 없이 주문 저장 (손님 주문 접수라 의도된 공개일 수 있음 → 오탐 판단 연습용) | 입력 검증·요청 제한 또는 의도된 공개임을 명시 |
| high | `nextjs-api-mutation-without-auth` | `app/api/webhook/route.ts` | 누구나 주문을 결제 완료로 바꿈 | 웹훅 서명 확인으로 해결 |
| high | `supabase-rls-disabled`, `config/supabase-rls-not-enabled` ×2 | `supabase/migrations/001_init.sql` | orders RLS를 끄고, reviews는 켜지 않음 | `enable row level security`와 정책 추가 |
| high | `config/env-file-committed` | `.env` | `.env`가 저장소에 올라감 | 저장소에서 지우고 키 재발급 |
| medium | `config/gitignore-missing-env` | `.gitignore` | `.env`가 무시 목록에 없음 | `.env` 추가 |
| high·medium | OSV: lodash 4.17.15 (6건) | `package-lock.json` | 프로토타입 오염·코드 주입 등 | lodash 4.17.21 이상 (`_.pick`만 쓰므로 영향 적음) |
| high·medium | OSV: jsonwebtoken 8.5.1 (3건) | `package-lock.json` | 서명 검증 우회 등 | jsonwebtoken 9 이상 |
| medium | `react-dangerously-set-inner-html` | `app/reviews/page.tsx` | 손님 후기 HTML을 그대로 보여 줌 (XSS) | 글자로만 보여 주거나 sanitize |
| low | `token-in-localstorage` | `app/admin/page.tsx` | 관리자 토큰을 localStorage에 저장 | httpOnly 쿠키 |
| low | `config/missing-security-headers` | `next.config.mjs` | 보안 헤더 없음 | `headers()`에 CSP 등 추가 |
| low | Gitleaks `jwt` ×2 | `.env` | 가짜 anon·service_role 키 | `.env` 삭제·재발급으로 함께 해결 |

## 시연에서 고칠 1건 추천

**SQL 인젝션(`app/api/orders/search/route.ts`)** 을 추천합니다. 한 줄 수정이고, 재검사에서 "해결됨"으로 바뀌는 것을 실제로 확인했습니다. 기획안의 e나무 사례(SQL 인젝션으로 주문자 정보 유출)와도 이어집니다.

service_role 키 문제는 더 극적이지만 고칠 곳이 여러 군데(화면 코드, 환경 변수, 키 재발급)라 2분 영상 안에 끝내기 어렵습니다. 화면에서 설명만 보여 주는 용도로 씁니다.

## GitHub에 올리기

1. **#69가 머지되면 허용한 소유자의 저장소만 검사됩니다.** 허용 목록에 있는 계정으로 공개 저장소를 만듭니다.
2. 로컬 저장소를 push합니다.
   ```bash
   cd C:\Users\alsgu\Dev\ymca-demo-flowershop
   git remote add origin https://github.com/<허용된 소유자>/<저장소 이름>.git
   git push -u origin main
   ```
3. `.env`에 가짜 JWT가 들어 있어 GitHub push protection이 막을 수 있습니다. 가짜 값이므로 안내 링크에서 허용하면 됩니다.
4. 시연 전에는 원래 상태로 되돌릴 수 있게 `main`은 그대로 두고, 고치는 작업은 매번 새 브랜치나 새 clone에서 합니다.

## LLM 해석 시간이 걱정되면

해석 대상이 많으면 공개 시연이 느려집니다(#59). 줄이려면 아래 파일을 지운 버전을 시연용으로 씁니다. 줄여도 핵심 이야기(서비스 키 노출, SQL 인젝션, RLS, 재검사)는 그대로 남습니다.

- `app/admin/page.tsx`, `app/api/admin/login/route.ts` (토큰·JWT 3건)
- `app/reviews/page.tsx` (XSS 1건)
- `package.json`의 `jsonwebtoken` (OSV 3건)
