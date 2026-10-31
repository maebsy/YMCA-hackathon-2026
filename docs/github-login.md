# GitHub 로그인

## 되는 일과 현재 범위

- GitHub 로그인·로그아웃·아이디 표시, 내부 상대 경로 `/api` 요청의 Supabase Bearer 전달과 401 안내입니다.
- `NEXT_PUBLIC_SUPABASE_URL`·`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` 둘 중 하나라도 없으면 로그인 UI·자동 인증 헤더를 끄고 기존 검사 동작을 유지합니다.
- 저장소 소유권·권한 확인은 다음 단계입니다. 사용자 저장소 실검증도 켜지 않습니다. `SCAN_REQUIRE_AUTH=false` 기본값을 유지합니다.
- Supabase 세션(access/refresh token)과 PKCE verifier는 브라우저에 보관합니다. GitHub `provider_token`·`provider_refresh_token`은 SDK 저장 경계에서 제거하며 별도로 저장하지 않습니다.
- 기존 검사 결과는 같은 브라우저에 남으며 로그아웃·계정 전환 시 지워지지 않습니다. 공용 기기에서 주의해야 하며, 비공개 저장소 지원 전에 결과 삭제·계정별 분리 방식은 **결정 필요**입니다.

## 먼저 확인할 호환성 (2026-11-01)

팀 결정은 **GitHub App** 자격 증명 사용입니다. GitHub App은 OAuth web application flow를 지원하며 Supabase와 같은 인증 endpoint를 사용합니다. 그러나 [Supabase GitHub 안내](https://supabase.com/docs/guides/auth/social-sign-in/auth-github)는 OAuth App만 명시하므로 GitHub App 구성이 공식 지원된다고 단정할 수 없습니다.
현재 [Supabase Auth provider 소스](https://github.com/supabase/auth/blob/7f36eb053286038d01ba1650dd48a15508550ce0/internal/api/provider/github.go)는 `user:email` scope를 요청하지만 [GitHub App 사용자 토큰 문서](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)는 App scope를 별도로 제한합니다. **Hosted Supabase와 GitHub App의 실제 로그인 호환성은 확인 필요**입니다. 이 PR은 실제 계정·자격 증명 연결을 수행하지 않았습니다.

## GitHub App 등록

1. GitHub Settings → Developer settings → GitHub Apps → New GitHub App에서 등록합니다. App ID·private key가 아닌 **Client ID·Client Secret**을 사용합니다.
2. Homepage URL은 현재 웹 주소, Callback URL은 Supabase 대시보드에 표시된 **`https://<project-ref>.supabase.co/auth/v1/callback`**로 설정합니다. 프런트 주소와 혼동하지 마세요.
3. Account permissions → **Email addresses: Read-only**를 설정합니다. Supabase가 `/user`와 `/user/emails`를 조회하기 때문입니다. 로그인만을 위해 저장소·조직 권한을 추가하지 않습니다([이메일 API 권한](https://docs.github.com/en/rest/users/emails#list-email-addresses-for-the-authenticated-user)).
4. 로그인용 토큰 만료는 기본 만료 설정을 유지할 수 있습니다. GitHub user token과 Supabase 세션은 별개이며 Supabase는 provider token을 자동 갱신하지 않습니다. 로그인만을 위해 만료 해제가 필요하다는 근거는 없습니다([GitHub 토큰 갱신](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens), [Supabase provider tokens](https://supabase.com/docs/guides/auth/social-sign-in#provider-tokens)).
5. **Client Secret은 Supabase 대시보드에만** 넣습니다. 저장소·프런트·서버 env에 넣지 않습니다.

## Supabase 설정과 돌아올 주소

1. Authentication → Sign In / Providers → GitHub를 켜고 GitHub App의 Client ID·Secret을 입력합니다. URL과 **publishable key**를 프런트 설정에 사용하며 service_role 키는 사용하지 않습니다.
2. URL Configuration의 Site URL을 실제 웹 origin으로 정합니다. Redirect URLs에는 돌아갈 페이지를 허용합니다. 로컬 예: `http://localhost:3000/**`; 공개 주소는 현재 소유한 정확한 origin과 필요한 경로만 등록합니다.
3. 로그인은 현재 페이지의 주소로 돌아오며 [PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow)의 `flowType=pkce`, `detectSessionInUrl=true`로 code를 자동 교환합니다. 로그인을 시작한 같은 브라우저·origin에서 돌아와야 verifier를 읽을 수 있습니다.
4. [Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls#use-wildcards-in-redirect-urls)는 wildcard를 지원합니다. `*`는 `.`·`/`를 넘지 않고 `**`는 넘습니다. 운영 경로는 필요한 범위만 허용합니다.
5. Cloudflare Quick Tunnel 주소가 바뀌면 Site URL·Redirect URLs를 새 정확한 origin으로 갱신하고 옛 주소는 제거한 뒤 새 주소에서 로그인을 다시 시작합니다. `*.trycloudflare.com`처럼 타인의 터널까지 포괄하는 허용 목록은 사용하지 않습니다([Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)). GitHub Callback URL은 Supabase 주소이므로 그대로입니다.

## 환경 변수와 켜는 순서

1. 로컬은 [`frontend/.env.example`](../frontend/.env.example)을 `frontend/.env.local`로 복사해 두 공개 값을 넣고 프런트를 빌드합니다. **Next.js `NEXT_PUBLIC_*`는 빌드 때 고정**되므로 변경 후 다시 빌드해야 합니다.
2. 일반 서버는 [`frontend.env.example`](../deploy/general-server/frontend.env.example)을 `~/.config/72hours/frontend.env`에 복사합니다. 이 파일의 공개 값을 `npm run build`를 실행하는 프로세스에도 적용하고 프런트 서비스를 시작합니다. systemd의 런타임 EnvironmentFile만 바꿔서는 이미 빌드된 브라우저 코드가 바뀌지 않습니다.
3. Compose는 루트 `.env`의 두 `NEXT_PUBLIC_*` 값만 프런트 build args·개발 환경으로 전달합니다. 값을 바꾸면 `docker compose up --build`로 다시 빌드합니다. DB 비밀번호·GPU 키·Client Secret은 프런트에 전달하지 않습니다.
4. 먼저 로그인·로그아웃과 현재 페이지 복귀를 실제 GitHub App으로 확인합니다. 호환성이 확인될 때까지 인증 필수 플래그를 켜지 않습니다.
5. 그다음 백엔드에 같은 프로젝트의 `SUPABASE_URL`·`SUPABASE_PUBLISHABLE_KEY`를 넣고 **`SCAN_REQUIRE_AUTH=true`로 바꾼 뒤 재시작**합니다. LLM 비동기 모드를 켤 필요는 없습니다. `LLM_JOBS_ENABLED=true`도 이미 인증을 요구하므로 별도 worker·스키마 활성화 절차를 따릅니다.
6. 두 인증 플래그가 모두 false면 Bearer가 있어도 검사·실검증 작업 소유자는 기존처럼 익명입니다. 사용자별 작업 접근 제한은 서버 인증을 켠 뒤 적용됩니다. 검증된 UUID를 쓰며, 토큰 내용을 프런트가 임의 판정하지 않습니다.

[`main.py`](../backend/app/main.py)의 `lifespan`은 `SCAN_REQUIRE_AUTH=true`, `LLM_JOBS_ENABLED=false`에서도 `prepare_auth`로 `job_auth`를 초기화합니다. [`test_auth_startup.py`](../backend/tests/test_auth_startup.py)는 실제 시작·종료를 검증합니다. `ActorDep`는 같은 검증 사용자를 실검증 작업의 owner로 연결합니다.

## 다음 단계

- GitHub 로그인은 저장소 소유권 확인이 아닙니다. GitHub App 설치·저장소별 권한 조회와 본인/권한자 판정 방식은 **결정 필요**입니다.
- 이후 GitHub API를 호출한다면 provider token의 보관·갱신 또는 설치 토큰 사용 방식을 별도로 설계해야 합니다. 이번 구현은 provider token을 저장·사용하지 않습니다.
- 실제 Supabase·GitHub App 연결, 운영 서버 로그인 성공, 저장소 권한 확인은 아직 검증하지 않았습니다.
