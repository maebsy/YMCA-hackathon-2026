# 일반 서버 실행 구성

일반 Linux 서버에서 웹 프록시·백엔드를 실행하고, **이미 실행 중인 GPU vLLM**에는 SSH 터널로 연결합니다. 프론트 소스, 기존 백엔드/compose, GPU 모델·서빙 프로세스는 수정하지 않습니다. 설치·서비스 시작은 명시적으로 나눕니다.

```text
인터넷 → HTTPS 진입점 → 프론트 127.0.0.1:3000 (별도 담당자)
                    └ /api/* → 백엔드 127.0.0.1:8000
                                    └ 127.0.0.1:8001 → SSH → GPU 127.0.0.1:8001/v1
```

## 실행 단위

| 서비스 | 범위 | 역할 |
|---|---|---|
| `72hours-gpu-tunnel` | systemd 사용자 서비스 | 전용 키·고정 호스트키·로컬 포워딩, 연결 종료 시 재시작 |
| `72hours-backend` | systemd 사용자 서비스 | 별도 release 가상환경, 단일 worker, 기존 API 실행 |
| `72hours-web` | systemd 사용자 서비스 | 로컬 `127.0.0.1:8080`, API와 프론트 경로 분리 |
| `72hours-frontend` | systemd 사용자 서비스 | Next.js 실행 예시, **설치 후 기본 비활성** |
| `72hours-public-web` | 선택적 systemd 시스템 서비스 | 도메인 HTTPS·시연용 인증, 80/443 바인딩 권한만 부여 |
| `72hours-quick-web` | 선택적 사용자 서비스 | 터널 전용 루프백 8088, 시연 계정 인증 |
| `72hours-quick-tunnel` | 선택적 사용자 서비스 | 승인된 Cloudflare 임시 HTTPS 진입점 |

`/healthz`는 프록시만, `/api/health`는 API/DB, `/api/llm/health`는 GPU 모델 연결을 확인합니다. 프론트가 없으면 일반 페이지는 502가 정상이며 이를 완성된 서비스로 표시하지 않습니다. 프론트는 상대 경로 `/api/...`를 사용하고 GPU 주소·키를 브라우저에 넣지 않습니다.

## 1. 런타임과 백엔드 준비

지원 환경: Linux x86_64, Python 3.12+, systemd, OpenSSH, `~/.local/bin/uv`. 기존 공용 `~/venv`와 시스템 Python 패키지는 바꾸지 않습니다. Caddy 2.11.7과 선택적 Node.js 24.19.0은 공식 배포 파일의 SHA-256/SHA-512 체크섬 확인 후 사용자 홈에 설치합니다.

```bash
python3 deploy/general-server/install-runtimes.py --with-node
# 팀에서 확정한 커밋을 git archive로 내보내 아래 별도 디렉터리에 풀어 두세요.
bash deploy/general-server/install.sh "$HOME/apps/72hours/releases/<커밋-SHA>"
```

설치기는 release별 `.venv`에 해당 커밋의 `backend/requirements.txt`를 설치하고 `~/apps/72hours/current` 심볼릭 링크를 바꿉니다. 이미 가상환경이 있는 release는 덮어쓰지 않습니다. 소스 경로는 `~/apps/72hours/releases/` 아래여야 합니다. 실행 중인 서비스는 자동 재시작하지 않으므로 이후 명시적으로 재시작해야 새 커밋이 적용됩니다.

## 2. GPU 연결과 비밀 설정

`~/.config/72hours/`는 권한 700, 내부 설정·개인키는 600으로 관리합니다.

1. 일반 서버 안에서 **별도** Ed25519 키 `~/.config/72hours/gpu-tunnel`을 만듭니다. 개인키를 PC나 GPU로 복사하지 않습니다.
2. GPU의 기존 `~/.ssh/authorized_keys`를 보존하고 새 공개키 한 줄만 등록합니다. 별도 승인이 필요한 자격증명 작업입니다. 예시 제한은 아래와 같습니다.

```text
from="<일반서버 사설IP>",restrict,port-forwarding,permitopen="127.0.0.1:8001",permitlisten="127.0.0.1:8001",command="/usr/bin/false" ssh-ed25519 <새 공개키> 72hours-general-server-tunnel
```

이 키는 일반 서버에서만 인증할 수 있고 명령·셸 실행은 거부됩니다. 로컬 포워딩 목적지는 vLLM으로 제한합니다. 원격 포워딩도 GPU의 루프백 8001만 허용하며, 현재 vLLM이 사용하는 포트입니다.

3. 기존에 신뢰한 SSH 연결을 통해 GPU의 **호스트 공개키**를 확인하고 `gpu_known_hosts`에 `<GPU 사설IP> ssh-ed25519 <호스트 공개키>`로 저장합니다. 검증 없이 `StrictHostKeyChecking=no`나 무검증 keyscan을 사용하지 않습니다.
4. `gpu-ssh.conf.example`을 `~/.config/72hours/gpu-ssh.conf`로 복사하고 GPU 주소·계정을 채웁니다.
5. `backend.env.example`을 `~/.config/72hours/backend.env`에 적용합니다. 기존 vLLM API 키를 승인된 SSH 경로의 표준입력으로 전달합니다. 터미널 출력·명령줄 인자·프론트 환경·Git에는 넣지 않습니다.

`DATABASE_URL`은 운영 DB 주소 또는 **release 밖의** SQLite 경로로 지정합니다. 예: `sqlite:////home/USER/.local/share/72hours/app.db`. Supabase를 쓸 때는 팀이 정한 주소를 쓰며 기존 DB를 초기화하거나 삭제하지 않습니다. 현재 백엔드의 테이블 생성 동작은 그대로입니다.

## 3. 일반 서버에서 실행

```bash
# SSH 로그아웃 이후와 재부팅 뒤에도 사용자 서비스를 유지합니다.
sudo loginctl enable-linger "$USER"
systemctl --user enable --now 72hours-gpu-tunnel 72hours-backend 72hours-web
curl --fail http://127.0.0.1:8080/api/health
curl --fail http://127.0.0.1:8080/api/llm/health
```

기본 웹 진입점은 루프백입니다. PC에서 임시 확인할 때는 `ssh -N -L 8080:127.0.0.1:8080 <일반 서버>` 후 `http://localhost:8080`을 사용합니다. 이 SSH 포워딩은 외부 공개가 아닙니다.

```bash
systemctl --user status 72hours-gpu-tunnel 72hours-backend 72hours-web
journalctl --user -u 72hours-backend -n 50 --no-pager
systemctl --user restart 72hours-backend   # 새 release 적용 시
systemctl --user stop 72hours-web 72hours-backend 72hours-gpu-tunnel
```

백엔드의 GPU 동시 요청 제한이 프로세스별이므로 기본은 worker 1개입니다. 웹 프록시의 응답 헤더 대기시간은 900초이며, 재시도를 많이 하는 LLM 작업이 이를 넘으면 요청이 실패할 수 있습니다. 장시간 작업을 공개 서비스에 제공할 때는 작업 큐·상태 조회가 별도로 필요합니다.

## 4. 프론트 담당자가 연결할 부분

프론트 코드는 이 변경에 포함하지 않습니다. 완성된 Next.js release를 `~/apps/72hours/frontend`가 가리키게 하고, 그 디렉터리에서 lockfile에 맞춰 의존성 설치와 build를 먼저 수행합니다. Node 경로는 `~/.local/share/72hours/node/bin`입니다.

```bash
export PATH="$HOME/.local/share/72hours/node/bin:$PATH"
cd "$HOME/apps/72hours/frontend"
npm ci
npm run build
systemctl --user enable --now 72hours-frontend
```

pnpm 등 다른 패키지 매니저나 Next.js standalone 출력이면 담당자가 실제 빌드 방식에 맞게 frontend unit을 조정해야 합니다. 이 unit은 일반 Next.js `next start` 예시입니다. 프론트 환경 파일은 `~/.config/72hours/frontend.env`로 분리하며 백엔드의 API 키를 복사하지 않습니다.

## 5. 외부 인터넷 공개

### 공인 IP와 도메인이 있는 경우

도메인의 DNS가 일반 서버를 가리키고 클라우드 ACG/NACL 및 서버 방화벽이 TCP 80/443을 허용해야 합니다. **사설 IP나 인터넷 출발지 NAT IP는 서비스 공인 IP와 다릅니다.** Ncloud에서는 [공식 메타데이터](https://api.ncloud-docs.com/docs/compute-vmetadata-serverdata)의 `http://169.254.169.254/latest/meta-data/publicIp`로 할당 주소를 확인할 수 있습니다. 빈 값이면 별도 공인 IP 또는 로드밸런서/터널 구성이 필요합니다.

1. `public-web.env.example`을 권한 600인 `~/.config/72hours/public-web.env`로 복사합니다.
2. `PUBLIC_DOMAIN`에 소유한 도메인을, `DEMO_USER`에 시연 계정을 지정합니다. `caddy hash-password`를 대화형으로 실행해서 얻은 해시만 `DEMO_PASSWORD_HASH`에 넣습니다. 파일은 shell에서 source하지 않습니다.
3. `bash deploy/general-server/install-public-web.sh`로 시스템 unit을 준비합니다. **이 명령은 서비스를 시작하지 않습니다.**
4. DNS/포트/설정 확인 후 `sudo systemctl enable --now 72hours-public-web`을 실행하고 외부 네트워크에서 HTTPS·인증·API를 확인합니다.

공개 unit은 일반 사용자로 실행하되 80/443 바인딩 capability만 받습니다. [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https)로 인증서를 발급하며, 이 방식은 공인 IP만 있는 경우의 신뢰 가능한 IP 인증서를 자동 보장하지 않습니다. 도메인이 필요합니다.

기존 데모 API에는 사용자 인증/프로젝트 접근 제어가 완성되지 않아 프록시에 [HTTP Basic 인증](https://caddyserver.com/docs/caddyfile/directives/basic_auth)을 둡니다. HTTPS에서만 사용하고, 앱의 인증·접근 제어가 준비되면 팀과 함께 교체합니다. Basic 인증은 앱의 Bearer Authorization 사용과 충돌할 수 있으므로 실제 로그인 연동 전에 제거/대체를 조율해야 합니다.

### 공인 IP가 없는 경우

운영진에게 공인 IP 또는 외부 로드밸런서 연결을 요청하거나, 사용자가 승인한 HTTPS 터널 서비스로 로컬 프록시를 연결할 수 있습니다. 외부 터널은 웹/API 요청·응답이 해당 제공자를 거치므로 선택과 승인을 받은 뒤 구성합니다. 기본 설치는 터널을 설치하거나 시작하지 않습니다.

사용자가 **Cloudflare Quick Tunnel을 통한 시연 공개를 승인한 경우** 다음 선택 기능을 사용합니다. GPU API 키는 터널의 설정이나 환경에 넣지 않습니다. Cloudflare 계정·도메인은 만들지 않으며, 서버의 8088 루프백 프록시만 연결합니다.

```bash
# Python 3.12 필요: libc bcrypt를 사용하며 crypt 모듈은 Python 3.13에서 제거됨
python3 deploy/general-server/prepare-quick-tunnel.py
systemctl --user enable --now 72hours-quick-web
curl -i http://127.0.0.1:8088/healthz  # 반드시 401이어야 함
# 서버 내부 ~/.config/72hours/demo-access.json의 시연 계정으로 200도 확인한 뒤:
systemctl --user enable --now 72hours-quick-tunnel
journalctl --user -u 72hours-quick-tunnel -n 80 --no-pager
```

준비 스크립트는 고정 버전 cloudflared를 공식 SHA-256으로 검증하고, 무작위 시연 비밀번호와 bcrypt 해시를 서버 내부에서 생성합니다. 원문 접속정보 `demo-access.json`과 Caddy용 `quick-web.env`는 권한 600이며 출력하거나 Git에 넣지 않습니다. 계정 원문은 시연 참가자에게 승인된 경로로만 전달합니다. 터널을 시작하기 전 무인증·오인증 401과 정상 인증 200을 확인하세요.

로그의 `https://...trycloudflare.com`이 임시 공개 주소입니다. 외부에서 `/healthz`, `/api/health`, `/api/llm/health`가 인증 후 200인지 확인합니다. `/`는 별도 프론트가 3000 포트에서 실행되기 전까지 502가 나옵니다. 이는 서버 연결 성공과 프론트 배포 완료가 다르다는 뜻입니다.

터널은 **재생성/프로세스 재시작 시 주소가 바뀝니다**. 종료는 `systemctl --user disable --now 72hours-quick-tunnel 72hours-quick-web`입니다. 재시작 후에는 로그에서 새 주소를 확인하고 이전 공유 주소를 갱신해야 합니다. 기존 로컬 프록시·백엔드·GPU는 이 명령으로 중지되지 않습니다.

[Quick Tunnel 공식 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/): 가용성 보장 없음, 동시 진행 요청 200개, SSE 미지원. 이 터널은 웹 시연용이며 기존 stdio MCP를 HTTP MCP로 바꾸지 않습니다. Cloudflare의 요청 시간 제한도 별도로 적용되므로 Caddy의 900초 설정만으로 긴 동기 LLM 호출 성공을 보장하지 않습니다. 실제 배포에는 고정 호스트·앱 인증·작업 큐를 별도로 구성해야 합니다.

## 검증과 변경 범위

```bash
python3 -m unittest discover -s deploy/general-server/tests -v
bash -n deploy/general-server/install.sh
bash -n deploy/general-server/install-public-web.sh
```

체크섬 테스트는 SHA-256/SHA-512, 변조·누락 시 설치 거부, 압축 경로 이탈 방지를 확인합니다. 서버에서는 Caddy validate, systemd-analyze verify, API/LLM health 및 임시 3000 포트 응답으로 프록시를 확인합니다. 임시 응답은 실제 프론트 구현이나 GPU 추론 검증이 아닙니다.

이 디렉터리 외에는 외부 자원 등록 문서만 변경합니다. 배포한 백엔드 커밋과 구성 커밋은 별도로 기록하고, Claude가 작업 중인 checkout이나 다른 서비스 프로세스를 배포 도구가 변경하지 않습니다.
