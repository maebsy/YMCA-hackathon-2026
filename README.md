# 72hours — 바이브 코더 보안 플랫폼
코디세이 AI 해커톤 2026 | 이노베이션아카데미 (2026.10.30 ~ 11.02)

> **"찾고, 고치고, 72시간 안에 끝냅니다."**  
> 비개발자·바이브 코더가 만든 웹 서비스의 보안 취약점을 4대 정밀 엔진으로 탐지하고, 로컬 GPU LLM의 **Red–Blue 자율 검증 루프**를 통과한 수정 프롬프트를 AI 코딩툴(MCP)로 즉시 전달해 법정 골든타임(24h·72h) 안에 조치와 리포트까지 완료하는 보안 플랫폼입니다.

- 🌐 **[브라우저에서 대시보드 바로 열기 (설치 불필요 · GitHub Live Preview)](https://htmlpreview.github.io/?https://github.com/maebsy/YMCA-hackathon-2026/blob/feat/frontend-live-sync-ux/docs/web-preview.html)** *(또는 [`docs/web-preview.html`](docs/web-preview.html)을 내려받아 브라우저로 실행)*
- 📐 **[시스템 플로우 및 보안 설계 문서](docs/system-flow.md)** *(브라우저용 다이어그램: [`docs/system-flow.html`](docs/system-flow.html))*

## 핵심 보안 아키텍처

| 단계 | 핵심 기술 및 보안 원칙 |
|---|---|
| **① 찾기 (4대 보안 엔진 & 즉시 파기)** | **Opengrep**(자체 바이브코딩 규칙 21개 + Aikido MIT) · **OSV-Scanner**(의존성 CVE) · **Gitleaks**(비밀키·커밋 이력) · **자체 설정 검사기**로 취약점을 정규화하며, 검사 직후 **원본 소스코드는 즉시 파기(Zero-Retention)**하고 결과·의존성 목록만 남깁니다. |
| **② 우선순위 & 고치기 (SSVC + GPU Red–Blue)** | CISA **SSVC**(`act` 지금 바로 · `attend` 이번 주 · `track*` 추후)로 우선순위를 분류합니다. 로컬 L4 GPU **vLLM(Qwen3.8-27B)**에서 **Blue**가 비개발자 눈높이 설명과 수정 패치를 작성하고, **Red**가 모의 공격으로 검증해 통과한 조치안만 전달합니다. |
| **③ AI 코딩툴 자동 전달 (MCP Handoff)** | 검사 결과를 MCP 서버(`integrations/mcp-handoff`)와 자동 동기화하여, Cursor · Claude Code 등에서 `list_findings`와 `get_fix_prompt`로 검증된 수정 지시를 바로 받아 패치합니다. |
| **④ 72시간 완료 리포트 & 24h·72h 신고 서포트** | 재검사 통과 시 비전공자용 **완료 리포트(`/api/reports/plain`)**를 발급하며, 침해사고·유출 의심 시 **KISA 침해사고(24시간)** 및 **개인정보보호위원회 유출(72시간)** 신고서 초안 작성을 지원합니다(미확인 항목은 `[확인 필요]`로 분리). |

---

## 개발 시작하기

```bash
git clone https://github.com/maebsy/YMCA-hackathon-2026.git
cd YMCA-hackathon-2026
bash scripts/setup-dev.sh
cp .env.example .env
```

## 구조

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI API 서버. DB는 SQLModel, 모든 API는 `/api` 아래 |
| `frontend/` | Next.js 16 대시보드, `/api/*`를 FastAPI로 프록시 |
| `security_engine/` | Opengrep · OSV-Scanner · Gitleaks · 자체 설정 검사기 통합 실행 및 정규화 엔진 |
| `integrations/mcp-handoff/` | 웹 검사 결과를 AI 코딩툴로 전달하는 로컬 MCP 서버 (`list_findings`, `get_fix_prompt`) |

DB는 `.env`의 `DATABASE_URL`로 정합니다. Docker 없이 실행할 때 비워 두면 SQLite, Compose에서는 로컬 PostgreSQL을 씁니다. Supabase 연결 문자열을 넣으면 팀 공용 DB를 사용합니다. SQLite는 Item 예제와 검사 응답 테이블을 자동 생성합니다. PostgreSQL의 검사 결과 저장에는 [저장 migration 적용](docs/scan-persistence.md)이 필요하며, 서비스 스키마·인증·비동기 큐는 [DB 설계](docs/db-erd.md)와 [활성화 절차](docs/async-llm.md)를 따릅니다.

## Docker로 실행 (권장)

[Docker Desktop](https://docs.docker.com/desktop/) 또는 Docker Engine + Compose v2.24.4 이상이면 Node.js·Python·PostgreSQL을 호스트에 따로 설치하지 않아도 됩니다.

```bash
cp .env.example .env              # 처음 한 번
docker compose up --build --watch
```

- 프론트 http://localhost:3000, API http://localhost:8000, 로컬 PostgreSQL이 같이 뜹니다. 프론트 주소의 http://localhost:3000/api/health 에서 `"db":"postgresql"`이 나오면 프록시와 DB 연결까지 성공입니다.
- 브라우저는 같은 주소의 `/api/*`로 요청하고 Next.js 서버가 `http://backend:8000`으로 전달합니다. 컨테이너 안의 `localhost`는 다른 서비스가 아닙니다.
- `frontend/src`, `frontend/public`, `backend/app` 저장 내용은 `--watch`로 반영됩니다. 프론트 package/lock/Next/TypeScript 설정과 백엔드 requirements 변경은 해당 이미지를 다시 빌드합니다. OS별 node_modules를 공유하지 않습니다.
- 끄기는 `Ctrl+C` 또는 `docker compose down`. DB 데이터는 남고, 지우려면 `docker compose down --volumes`
- `.env`의 `DATABASE_URL`이 비어 있으면 로컬 DB를, Supabase 주소가 있으면 그 DB를 씁니다
- DB만 Docker로 쓰고 서버는 직접 띄워도 됩니다: `docker compose up db` 후 `.env`에 `DATABASE_URL=postgresql://app:app@localhost:5432/app`. 이 값은 컨테이너 안에서 통하지 않으니 전체를 Docker로 띄울 때는 다시 비우세요
- 프론트 컨테이너에는 루트 `.env`를 전달하지 않습니다. DB 비밀번호·GPU 키는 백엔드에만 전달하며, 모든 호스트 포트는 127.0.0.1에만 엽니다.

### 빌드한 프론트로 통합 시연

```bash
docker compose -f compose.yaml -f compose.production.yaml up --build --detach --wait
```

이 모드는 Next.js standalone 빌드와 정적 파일만 담은 비root 컨테이너를 사용하며, 백엔드 reload와 양쪽 watch를 끕니다. 종료도 같은 `-f` 두 개를 사용합니다. 개발 모드로 돌아갈 때는 기본 `docker compose up --build --watch`를 실행합니다. [Next.js Docker 배포 방식](https://docs.docker.com/guides/nextjs/)

프록시 주소는 배포 **빌드 시** 확정됩니다. Compose의 `frontend.build.args.BACKEND_ORIGIN`을 바꾸면 이미지를 다시 빌드해야 합니다. Docker 없이 실행하면 기존 `127.0.0.1:8000` 기본값과 `npm run build/start`가 유지되며, 필요하면 서버 환경 변수 `BACKEND_ORIGIN`을 설정합니다. 브라우저 공개 변수(`NEXT_PUBLIC_*`)는 사용하지 않습니다.

이 구성은 기존 일반 서버의 systemd/Caddy/GPU 터널을 자동 전환하지 않습니다. 공개 시연은 기존 인증 프록시를 거쳐 연결해야 합니다. 현재 프론트의 예제 데이터·OAuth·스캔 접수 같은 기능 통합은 별도 작업이며 Compose 기동이 전체 서비스 연동 완료를 뜻하지는 않습니다. Supabase를 지정해도 기본 Compose의 개발 DB 컨테이너는 함께 뜨지만 API는 지정한 Supabase에 연결합니다. 비동기 모드는 스키마와 별도 worker 준비 후 활성화합니다.

문제가 생기면:

| 증상 | 해결 |
|---|---|
| `port is already allocated` | `.env`에서 `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT`를 다른 번호로 |
| 컨테이너에서 LLM 서버에 연결 안 됨 | 내 PC에 8001 SSH 터널이 열려 있는지 확인하세요(아래 "LLM 서버 연결"). 다른 주소를 쓰려면 `.env`의 `DOCKER_LLM_BASE_URL` |
| 나만 설정을 바꾸고 싶음 | `compose.override.yaml`을 만들면 자동으로 합쳐지고 커밋되지 않습니다 |

## 백엔드 실행 (Docker 없이)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- http://localhost:8000/api/health 에서 `{"status":"ok","db":"sqlite"}`가 나오면 성공 (Supabase면 `"postgresql"`)
- http://localhost:8000/docs 에서 API를 직접 눌러 볼 수 있습니다
- `Item`과 `/api/items`는 연결 확인용 예시입니다. 실제 테이블을 만들면 지우세요.

## LLM 서버 연결 (vLLM, 8001 포트)

GPU 서버의 vLLM은 **8001 포트**로 띄웁니다. 백엔드(8000)와 겹치지 않게 서버와 내 PC 모두 같은 번호를 씁니다.

```bash
# GPU 서버: 처음 한 번 setup-gpu.sh, 그다음 serve.sh. 127.0.0.1에만 열고 API 키를 요구합니다
bash scripts/llm/setup-gpu.sh
tmux new -d -s vllm 'bash scripts/llm/serve.sh'

# 내 PC: 서버의 8001을 내 PC의 8001로 가져옵니다 (SSH 터널 허용 여부는 운영진 확인 필요)
ssh -N -L 8001:127.0.0.1:8001 <GPU 서버>
```

- 백엔드를 직접 띄우면 `.env`의 `LLM_BASE_URL=http://localhost:8001/v1`을 그대로 씁니다
- Docker로 띄우면 compose가 `http://host.docker.internal:8001/v1`(내 PC의 8001)로 바꿔 연결합니다
- vLLM은 OpenAI 호환 API라, 개발 중에는 OpenAI·Ollama 주소로 바꿔도 코드는 그대로입니다
- 모델(Qwen3.8-27B), Red–Blue 흐름, API, 테스트 방법: [docs/llm.md](docs/llm.md)

## 리포트·신고서

- 비전공자용 점검 리포트(완료 리포트 포함)와 KISA 침해사고 신고(24시간)·개인정보 유출 신고(72시간) 초안: [docs/reports.md](docs/reports.md)
- `POST /api/reports/plain` · `/assess` · `/incident-24h` · `/privacy-72h`, `?format=json|markdown|html`

## 규칙

- 이슈·브랜치·커밋·PR 규칙: [CONTRIBUTING.md](CONTRIBUTING.md)
- 외부 자원 활용 내역: [docs/external-resources.md](docs/external-resources.md)
