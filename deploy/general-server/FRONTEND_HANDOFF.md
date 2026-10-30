# 프론트 담당자 인수인계

확인 기준: 2026-10-31 05시경 KST. 실제 서버와 배포된 OpenAPI 기준이며 작업 중인 브랜치의 API와 다를 수 있습니다. 공개 URL과 시연 비밀번호는 운영자가 별도로 전달합니다. 비밀번호·개인키는 Git에 올리지 않습니다.

## 1. 현재 준비 상태

| 항목 | 확인 결과 |
|---|---|
| 일반 서버 | `10.1.1.15:22`, 사용자 `ncloud`, 홈 `/home1/ncloud` |
| SSH 접근 | VPN 필요. 본인의 등록된 SSH 키 사용 |
| 외부 웹 접근 | Cloudflare 임시 HTTPS 주소, VPN 불필요, 시연용 Basic 인증 필요 |
| 공인 IP | Ncloud 메타데이터의 할당 공인 IP 값이 비어 있음 |
| 런타임 | Node `v24.19.0`, npm/npx `11.17.0`; 사용자 홈에 설치 |
| 프론트 | 아직 미배포. `frontend` 경로 없음, 서비스 disabled/inactive, 3000 리스너 없음 |
| 백엔드 | `26af8bb7eee813ef2c3f362e8eba593d8ddcfd19` 스냅샷 실행 중 |
| DB | 서버 로컬 SQLite. 팀 Supabase 연결은 아직 없음 |
| GPU | 기존 vLLM `qwen3.8-27b`, 전용 SSH 터널로 연결 |
| 외부 검증 | 무인증/오인증 401, 정상 인증의 `/healthz`, `/api/health`, `/api/llm/health` 200 |
| 첫 화면 `/` | 현재 502. 프론트 배포 후 다시 확인 필요 |

현재 검증은 연결·인증·모델 목록 확인까지입니다. 실제 LLM 생성, 실제 프론트 빌드, 전체 사용자 흐름은 검증하지 않았습니다. npm 링크 복사 오류는 공식 체크섬 검증 설치본으로 복구했고 Node/npm/npx 실행, 의존성 없는 임시 프로젝트의 `npm ci`, Linux 회귀 테스트 4개를 확인했습니다. 아래 Bash 블록은 Linux에서 문법 검사를 통과했습니다.

## 2. 서버 접속

PC에서 VPN 연결 후 본인의 등록된 키 경로로 실행합니다. `hk-server`는 기존 운영자 PC의 별칭이므로 다른 PC에는 없을 수 있습니다.

```powershell
ssh -i "$HOME/.ssh/<본인의_등록된_키>" ncloud@10.1.1.15
```

확인한 ED25519 호스트 키 지문: `SHA256:Zm5aAv5DJ/EnKiObKSadOxA5nKuXgToCGhNiyhVhAjY`. 처음 접속 시 대조하고, 다르면 운영자에게 확인합니다. 접속 권한이 없으면 본인 공개키 등록을 요청합니다. 기존 운영자의 개인키를 공유하지 않습니다. 웹용 시연 비밀번호로 SSH 로그인할 수는 없습니다.

서버에서 실행:

```bash
export PATH="$HOME/.local/share/72hours/node/bin:$PATH"
node --version
npm --version
systemctl --user status 72hours-backend 72hours-frontend --no-pager
curl --fail http://127.0.0.1:8080/api/health
```

`sudo systemctl`이 아니라 **`systemctl --user`**를 사용합니다. 사용자 linger는 이미 켜져 있어 SSH 로그아웃 후에도 서비스가 유지됩니다.

## 3. 프론트 배포

현재 unit은 **일반 Next.js `next build` → `next start` 방식**입니다. main의 `frontend/`는 아직 `.gitkeep`뿐이므로 아래 명령은 프론트 코드가 준비된 커밋에서 실행합니다. 다른 프레임워크, pnpm/yarn, 모노레포, standalone/static export라면 패키지 설치·빌드·unit 실행 경로를 담당자와 먼저 맞춥니다. 서버에 `npm run dev`를 상시 실행하지 않습니다. [Next.js 배포 문서](https://nextjs.org/docs/app/getting-started/deploying)

사전 조건: 프론트 담당자와 배포 시점을 맞추고, 검증할 **40자리 커밋 SHA**를 정합니다. 저장소 루트의 `frontend/`가 독립 npm 프로젝트이며 `package-lock.json`, `build: next build`가 있다는 전제입니다. 작업 중인 checkout을 가져오지 않고 별도 release에 해당 커밋을 받습니다.

서버 Bash에서 아래 블록의 SHA 한 곳을 바꿔 실행합니다. 이 블록은 빌드 실패 시 기존 프론트를 바꾸지 않습니다.

```bash
(
set -euo pipefail
umask 077
export PATH="$HOME/.local/share/72hours/node/bin:$PATH"
FRONTEND_REV='<프론트가_포함된_40자리_커밋_SHA>'
[[ "$FRONTEND_REV" =~ ^[0-9a-f]{40}$ ]]
app_root="$HOME/apps/72hours"
mkdir -p "$app_root/frontend-releases"
exec 9>"$app_root/frontend-deploy.lock"
flock -n 9
release="$app_root/frontend-releases/$FRONTEND_REV-$(date +%Y%m%d%H%M%S)"
test ! -e "$release"
git clone --no-checkout https://github.com/maebsy/YMCA-hackathon-2026.git "$release"
git -C "$release" checkout --detach "$FRONTEND_REV"
test "$(git -C "$release" rev-parse HEAD)" = "$FRONTEND_REV"
cd "$release/frontend"
test -f package.json
test -f package-lock.json
npm ci --include=dev
# 프로젝트에 빌드 시 환경변수가 필요하면 여기서 설정한 후 build합니다.
npm run build
test -f .next/BUILD_ID
test -f node_modules/next/dist/bin/next
previous=''
if [[ -L "$app_root/frontend" ]]; then
  previous="$(readlink -f "$app_root/frontend")"
elif [[ -e "$app_root/frontend" ]]; then
  echo 'frontend가 관리되지 않는 실제 디렉터리입니다. 운영자 확인 필요.' >&2
  exit 1
fi
printf '%s\n' "$previous" > "$release/previous-frontend.txt"
ln -s "$release/frontend" "$app_root/frontend-next-$$"
mv -Tf "$app_root/frontend-next-$$" "$app_root/frontend"
systemctl --user enable 72hours-frontend
systemctl --user restart 72hours-frontend
printf '배포 경로: %s\n이전 경로: %s\n' "$release/frontend" "$previous"
)
```

`frontend.env`는 선택적인 **실행 시** 환경 파일 `~/.config/72hours/frontend.env`입니다(권한 600). systemd는 빌드 셸에 이 파일을 자동 주입하지 않습니다. `NEXT_PUBLIC_*` 등 빌드에 필요한 값은 build 전에 프로젝트 방식으로 설정해야 하며, 공개 변수에는 비밀값을 넣지 않습니다. GPU API 키는 프론트에 필요하지 않습니다.

프론트 서비스의 실행 경로는 `~/apps/72hours/frontend`, 리스닝 주소는 `127.0.0.1:3000`입니다. Next standalone 등으로 unit을 바꾼 경우에만 `systemctl --user daemon-reload` 후 frontend를 재시작합니다. 프론트 배포에 backend/GPU/Caddy/Cloudflare 재시작은 필요하지 않습니다. 특히 quick-tunnel을 재시작하면 공유 URL이 바뀝니다.

배포 후 확인:

```bash
systemctl --user is-active 72hours-frontend
journalctl --user -u 72hours-frontend -n 60 --no-pager
curl --fail --retry 10 --retry-connrefused --retry-delay 1 --max-time 10 http://127.0.0.1:3000/
curl --fail http://127.0.0.1:8080/
curl --fail http://127.0.0.1:8080/api/health
```

그다음 외부 브라우저로 시연 URL에 로그인하여 첫 화면, JS/CSS, 새로고침/상세 경로, API 호출을 확인합니다. 서버 내부 200만으로 외부 화면 배포 완료로 판정하지 않습니다.

복구: 직전 배포 출력의 `이전 경로` 또는 해당 release의 `previous-frontend.txt`를 확인합니다. 아래는 기존 배포가 있는 경우만 사용합니다. 첫 배포 실패면 frontend만 중지하고 로그를 확인합니다.

```bash
(
set -euo pipefail
app_root="$HOME/apps/72hours"
PREVIOUS_FRONTEND='<확인한_이전_release의_frontend_절대경로>'
case "$PREVIOUS_FRONTEND" in "$app_root/frontend-releases/"*/frontend) ;; *) exit 1 ;; esac
test -f "$PREVIOUS_FRONTEND/.next/BUILD_ID"
test -L "$app_root/frontend"
exec 9>"$app_root/frontend-deploy.lock"
flock -n 9
ln -s "$PREVIOUS_FRONTEND" "$app_root/frontend-rollback-$$"
mv -Tf "$app_root/frontend-rollback-$$" "$app_root/frontend"
systemctl --user restart 72hours-frontend
)
```

## 4. API 연결

브라우저에서는 **동일 출처의 상대 경로 `/api/...`**를 사용합니다. 임시 공개 호스트명을 코드에 박아 넣거나 브라우저에서 `localhost:8000`, GPU 주소로 호출하지 않습니다.

```text
브라우저 → 공개 HTTPS → Basic 인증 → /api/* → FastAPI 127.0.0.1:8000
                                └ 나머지 → Next.js 127.0.0.1:3000
```

**`/api`와 `/api/*`는 전부 FastAPI 전용입니다.** Next.js의 `/api/auth`, BFF route handler도 이 경로로 만들면 공개 환경에서 Next에 도달하지 않습니다. 별도 prefix를 사용하거나 인프라 담당자와 라우팅을 조정해야 합니다.

| 현재 배포된 API | 용도·주의 |
|---|---|
| `GET /api/health` | `{"status":"ok","db":"sqlite"}` |
| `GET /api/llm/health` | 모델 연결 확인, 생성 완료를 의미하지 않음 |
| `POST /api/llm/explain` | finding 1~50개 → 동기 LLM 해석. 개발/평가용 계약 |
| `GET/POST /api/items` | 초기 예제 CRUD. 프로젝트/검사 API로 사용하지 않음 |

스캔 업로드, 프로젝트, 리포트, 작업 상태 조회 API는 **현재 배포본에 없습니다**. 스캔엔진·DB·비동기 API는 후속 작업입니다. 공개 `/docs`와 `/openapi.json`도 현재 FastAPI로 라우팅하지 않습니다. 실제 규격은 SSH로 `curl http://127.0.0.1:8000/openapi.json`을 조회합니다.

연결 확인용 브라우저 코드:

```javascript
const response = await fetch('/api/health', {
  credentials: 'same-origin', cache: 'no-store'
});
if (!response.ok) throw new Error(`API 연결 실패: ${response.status}`);
console.log(await response.json());
```

최초에 시연 URL의 `/healthz`를 브라우저로 열어 전달받은 Basic 계정으로 로그인합니다. JS에서 시연 비밀번호를 저장하거나 `Authorization`을 직접 만들지 않습니다. 이 구성에서 앱의 `Authorization: Bearer ...`를 붙이면 Basic 인증과 충돌합니다. 실제 사용자 인증은 #26/#7과 함께 설계해야 하며, 대체 인증 없이 보호 장치를 먼저 제거하지 않습니다.

서버 컴포넌트에서 API를 부를 경우 서버 전용 주소 `http://127.0.0.1:8000`을 사용할 수 있습니다. 이는 프록시 Basic 인증을 우회하는 내부 호출이므로 향후 사용자·프로젝트 권한 확인을 별도로 구현해야 합니다. 이 주소는 브라우저용 환경변수가 아닙니다.

## 5. LLM 요청과 화면 계약

아래는 **요청 형식 예시**이며 자동으로 실행하는 health check가 아닙니다. GPU 사용 시점을 맞춘 후 1건부터 검증합니다. `mode=blue`는 설명 확인용, `red_blue`는 Red 검증 포함이며 기본값입니다.

```json
{
  "mode": "blue",
  "findings": [{
    "fingerprint": "demo-config-001",
    "tool": "semgrep",
    "category": "config",
    "rule_id": "demo.debug-enabled",
    "title": "운영 설정에서 디버그 모드 활성화",
    "severity": "medium",
    "file_path": "example/settings.py",
    "start_line": 1,
    "snippet": "DEBUG = True"
  }]
}
```

필수 finding 필드는 `fingerprint`, `tool`, `category`, `rule_id`, `title`, `severity`입니다. category는 `dependency|code|secret|config`, severity는 `critical|high|medium|low|info|unknown`입니다. 실제 비밀값·개인정보를 샘플에 넣지 않습니다.

응답은 `{mode, model, prompt_version, latency_ms, results:[...]}`입니다. HTTP 200이어도 **각 항목의 `status`**를 확인합니다.

| 항목 | 화면 처리 |
|---|---|
| `status=done` | `explanation`의 summary, why_risky, priority, fix_steps 표시 |
| `status=failed` | 실패 표시와 명시적 재시도. 원본 `error`를 그대로 사용자에게 노출하지 않음 |
| `status=skipped` | reason 표시. 실패와 구분 |
| `needs_manual_review=true` / 오탐 의심 | 수동 확인 안내. 자동 수정 완료로 표시하지 않음 |
| `ai_fix_prompt` | 전달 조건 확인 후 복사/MCP 제공 후보로 사용 |
| HTTP 422 | 요청 필드·개수 오류. detail을 보고 요청 수정 |
| HTTP 503 | GPU 연결 실패 가능. 일반적인 재시도 안내 |
| HTTP 401 | 시연 인증 실패 또는 Bearer/Basic 충돌 확인 |
| 502/504/524·연결 끊김 | 프록시/실행 상태 확인. GPU 작업 취소로 간주하지 않음 |

버튼 중복 실행을 막고 로딩/실패/부분 성공을 구분합니다. 현재 요청은 오래 걸릴 수 있고, 브라우저 취소·네트워크 timeout이 서버 작업 취소를 보장하지 않습니다. 무조건 자동 재시도하지 않습니다. 운영 흐름은 #26의 백그라운드 작업 + 상태 polling으로 전환해야 합니다.

MCP로 수정 지시를 넘길 조건은 [PR #23](https://github.com/maebsy/YMCA-hackathon-2026/pull/23)의 구현에 맞춥니다: done, variant D, red_verdict pass, 마지막 red_round도 pass 및 issues 없음, needs_manual_review/false_positive_suspect 모두 false, fingerprint 일치 및 유효한 ai_fix_prompt/버전 정보. **Blue 예시 결과는 MCP 자동 전달 대상이 아닙니다.** Red pass 자체가 실제 코드 수정·취약점 해결 완료를 의미하지 않습니다.

현재 MCP는 결과 JSON 파일을 읽는 별도 **로컬 stdio** 방식입니다. 이 공개 웹 URL은 MCP endpoint가 아니며, 웹 버튼이 사용자 AI 에이전트를 자동 실행하지 않습니다. 결과 JSON과 검사 대상 저장소·커밋 정보를 연결하고 사용자가 MCP를 등록·호출하는 흐름이 필요합니다.

## 6. 로컬 프론트 개발

VPN + SSH 권한이 있는 PC에서 별도 터미널에 포워딩을 유지합니다.

```powershell
ssh -i "$HOME/.ssh/<본인의_등록된_키>" -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8800:127.0.0.1:8000 ncloud@10.1.1.15
```

로컬 개발 서버의 `/api/:path*`를 `http://127.0.0.1:8800/api/:path*`로 프록시/rewrite합니다. 브라우저는 계속 상대 경로 `/api/...`를 사용합니다. CORS 설정을 열거나 시연 비밀번호를 프론트 소스에 넣을 필요가 없습니다. 이 SSH 포워딩은 본인 PC 루프백에서만 열립니다. 로컬에서는 `http://127.0.0.1:8800/docs`로 FastAPI 문서도 확인할 수 있습니다.

## 7. 운영 확인과 다음 작업

공개 주소가 바뀌었는지 확인할 때는 아래 로그의 **최근 터널 시작에 대응하는 URL**을 봅니다. 서비스가 active인지와 외부 health 응답을 함께 확인합니다. 오래된 로그의 URL을 재공유하지 않습니다.

```bash
systemctl --user is-active 72hours-quick-tunnel
journalctl --user -u 72hours-quick-tunnel -n 100 --no-pager -o cat
# 셸 변수에 운영자가 확인한 현재 주소 입력. 비밀번호는 curl 프롬프트에서 입력.
DEMO_URL='https://<현재주소>.trycloudflare.com'
curl --fail --user demo "$DEMO_URL/healthz"
curl --fail --user demo "$DEMO_URL/api/health"
```

[Quick Tunnel 공식 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/): 재생성 시 호스트명 변경, 가용성 보장 없음, 동시 진행 요청 200개, SSE 미지원. 프록시의 900초 설정만으로 공개 인터넷의 긴 LLM 요청 성공을 보장할 수 없습니다.

아래 우선순위는 **다음 작업 제안**이며 기존 이슈의 라벨이나 담당자를 바꾸지는 않았습니다.

| 순서 | 담당 영역·기존 이슈 | 다음 작업과 완료 기준 |
|---|---|---|
| P0 | 프론트 담당 | 실제 스택/커밋 확정 → 빌드·3000 배포 → 외부 첫 화면/자산/상세 경로/API 확인 |
| P0 | 인프라 [#24/PR #25](https://github.com/maebsy/YMCA-hackathon-2026/pull/25) | 리뷰 승인 후 규칙대로 squash merge. 현재 서버 실행과 main 반영 상태를 구분 |
| P0 | 백엔드 [#26](https://github.com/maebsy/YMCA-hackathon-2026/issues/26), DB [#7](https://github.com/maebsy/YMCA-hackathon-2026/issues/7) | 작업 생성·상태 조회·결과 저장, 사용자/프로젝트 권한 검증, Basic 대체. timeout 없이 진행/실패/완료 표시 |
| P0 | 엔진 [#15/PR #21](https://github.com/maebsy/YMCA-hackathon-2026/pull/21) | 검사 결과 저장→LLM 작업→리포트 연결. 승인된 통합 커밋으로 별도 백엔드 release 배포 후 API 계약 재확인 |
| P0 | 프론트·AI [#28](https://github.com/maebsy/YMCA-hackathon-2026/issues/28), [#27/PR #29](https://github.com/maebsy/YMCA-hackathon-2026/pull/29) | 미검사 영역·수동 확인·실패 표시, 패키지 단위 결과 계약 확인. 기존 담당자 작업과 조율 |
| P1 | MCP [#22/PR #23](https://github.com/maebsy/YMCA-hackathon-2026/pull/23) | 검증 통과 결과 export + 대상 저장소/SHA 연결 → 사용자 에이전트 조회 → 수정/테스트/재검사 1건 시연 |
| P1 | 통합 검증 | 실제 1건의 Blue/Red–Blue 지연·오류·결과 품질 측정, 외부 화면부터 재검사까지 확인 |
| P1 | 운영 | 고정 호스트/접근 인증, DB 백업·복구, 오류 로그·디스크·GPU 상태 점검 기준 확정 |

작업은 **이슈 → 최신 main 기반 브랜치 → PR → 승인 1명·검사 통과 → squash merge** 순서를 지킵니다. 프론트/API 구현은 각 담당자 브랜치에서 진행하고, 운영 서버의 `current`, GPU vLLM, 다른 작업자의 checkout을 프론트 배포 명령으로 변경하지 않습니다.
