# 72hours — 바이브 코더 보안 플랫폼
> **"찾고, 고치고, 72시간 안에 끝냅니다."**  
> 코디세이 AI 해커톤 2026 | 이노베이션아카데미 (2026.10.30 ~ 11.02)

[![Smart Aqua Live Demo](https://img.shields.io/badge/72hours-Smart_White_·_Light_Blue_·_Light_Mint-0284C7?style=for-the-badge&logo=vercel&logoColor=white)](https://codepen.io/lucidweb777/full/myWzqwa)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.4.3-0F172A?style=for-the-badge&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162.0-0D9488?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![GPU vLLM](https://img.shields.io/badge/GPU_LLM-vLLM_L4_(Qwen3.8--27B)-2DD4BF?style=for-the-badge&logo=nvidia&logoColor=black)](docs/llm.md)

---

## 🌐 스마트 화이트 × 라이트블루 × 라이트민트 미니멀 레이아웃 & 120fps 물결 스캔 인터랙션

> **"맑은 물결로 채우는 0% → 100% 스마트 보안"** — **화이트(`#FFFFFF`) · 라이트블루(`#E0F2FE`~`#0284C7`) · 라이트민트(`#CCFBF1`~`#0D9488`)** 를 조화롭게 결합한 미니멀 보안 스튜디오 레이아웃입니다.  
> 초기 진입 및 스캔 실행 시 **중앙 검색창 왼쪽(`0%`)부터 오른쪽(`100%`)까지 120fps Direct-DOM 엔진으로 맑은 물결(Liquid Wave)이 차오르는 애니메이션**과 **하단의 `0% ~ 100%` 카운트업(Count-up) 애니메이션**이 끊김 없이 1:1 동기화됩니다. 또한 복잡한 텍스트를 줄이고 **슬라이드 버튼(`◀ / ▶`) · 우측 슬라이드 드로어 · 호버 툴팁(`ⓘ`)** 으로 전체 컨텐츠를 미니멀하게 탐색할 수 있습니다.

![YMCA 72hours Smart Aqua Layout Preview](docs/assets/neo-sumuk-layout.svg)

### 📐 사이트 전체 UI/UX 레이아웃 구조 (120fps 물결 검색창 & 슬라이드·툴팁 미니멀 구조)

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [72h] 72hours · 스마트 보안 스튜디오    [01 스캔] [02 흐름·평가] [03 신고서] [04 리포트] [💧 120fps 로딩 시연] │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [HERO & LOADING STAGE : 120fps 중앙 물결 차오름(Liquid Fill) 검색창 × 하단 0%~100% 카운트업 1:1 동기화]      │
│                         맑은 물결로 채우는 0% → 100% 스마트 보안                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ [🔍] https://github.com/minji-cafe/order-site  ~~~~~~~~~~~~~~~~🌊 (좌→우 120fps 물결)   [✨ 스캔]  │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ ● 120FPS DIRECT-DOM SYNC : ③ 로컬 L4 GPU Red–Blue 검증 루프 가동                         [ 78% ]   │  │
│  │ [████████████████████████████████████████████████████████████░░░░░░░░░░]                           │  │
│  │ [   ① 추출 ✓   ]       [  ② 4대 엔진 ✓  ]       [ ③ GPU 검증 (78%) ]       [     ④ 완료     ]     │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────┐ ┌────────────────────────┐ ┌────────────────────────┐ ┌───────────────────┐  │
│  │ 72H 타이머 ⓘ  61:12:40 │ │ 즉시 조치(act) ⓘ  1건  │ │ GPU 성공률 ⓘ     96%   │ │ 원본 즉시 파기 100%│  │
│  └────────────────────────┘ └────────────────────────┘ └────────────────────────┘ └───────────────────┘  │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [SLIDE BAR]  [◀ 이전 슬라이드]  [01 취약점 스캔 & MCP] [02 5단계 흐름 & GPU] [03 신고 코파일럿] [04 리포트] [다음 ▶] │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [SLIDE 01 : 좌측 스캔 환경 설정 (GitHub 연동 단일) + 우측 미니멀 취약점 리스트 & 우측 슬라이드 드로어]      │
│ ┌──────────────────────────────────────────┐ ┌─────────────────────────────────────────────────────────┐ │
│ │ 스캔 환경 설정            [엔진 로그 ⓘ]  │ │ [전체 (5)] [act · 지금 바로] [attend · 이번 주] [track*] │ │
│ │ 채널: [          GitHub 연동           ] │ │ ┌─────────────────────────────────────────────────────┐ │ │
│ │ 환경: [Windows] [macOS] [Linux] / Vercel │ │ │ [act · 지금 바로]  src/lib/supabase.ts:4 · gitleaks │ │ │
│ │ [💧 0%→100% 물결 스캔 실행]              │ │ │ 브라우저 코드에 관리자 키(service_role) 노출 [상세▶]│ │ │
│ │ [⑤ 수정 반영 후 재검사 ↺]                │ │ └─────────────────────────────────────────────────────┘ │ │
│ │ [MCP 자동 저장 핸드오프: list/get_prompt]│ │ ★ 카드 클릭 시 우측 슬라이드 드로어(Slide-Over) 열림:    │ │
│ └──────────────────────────────────────────┘ │   Red 공격 시나리오 + OS 명령어 + GPU 검증 AI 프롬프트   │ │
│                                              └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 📱 핵심 인터랙션 및 4대 슬라이드 상세

| 구분 | 핵심 구성 화면 및 화이트·라이트블루·라이트민트 미니멀 UX | 주요 기능 및 저장소 연동 내역 |
|---|---|---|
| **120fps 중앙 물결 검색창 & 카운트업**<br>(`LiquidSearchBox`) | • **120fps 무지연 좌→우 물결 차오름**: React 리렌더링 없이 Direct-DOM `useRef` + GPU 가속으로 라이트블루(`#38BDF8`)~라이트민트(`#2DD4BF`) 물결이 `0%`→`100%` 차오름<br>• **하단 `0% ~ 100%` 카운트업 1:1 동기화**: 상단 검색창 물결 폭(`width`)과 소수점 단위까지 동기화되어 숫자가 카운트업되며 4단계 미니멀 칩이 순차 점등 | • 페이지 첫 진입 시 인트로 로딩 모달 및 히어로 중앙 검색창 양쪽 모두에서 작동<br>• 상단 헤더의 `💧 120fps 로딩 시연` 버튼으로 언제든 재시연 가능 |
| **슬라이드 01: 취약점 스캔 & MCP**<br>(`activeSlide = 0`) | • **좌측 스캔 환경 설정**: **`GitHub 연동` 단일 채널**, OS(Windows/macOS/Linux)·호스팅 선택, 엔진 로그 팝오버(`ⓘ`), **MCP 자동 저장(`McpHandoff`)**<br>• **우측 미니멀 취약점 카드 & 우측 슬라이드 드로어**: 카드를 클릭하면 오른쪽에서 슬라이드 패널이 열리며 Red 공격 시나리오·OS 명령어·AI 프롬프트 표시 | • 실제 백엔드 `/api/scans` 및 `/api/llm/explain` 연동<br>• `list_findings` / `get_fix_prompt` MCP 핸드오프 파일 자동 갱신 |
| **슬라이드 02: 5단계 흐름 & GPU 평가**<br>(`activeSlide = 1`) | • **5단계 미니멀 카드(툴팁 `ⓘ`)**: `STEP 01` ~ `STEP 05` 핵심 요약 및 마우스 호버 상세 툴팁<br>• **로컬 L4 GPU 비교군(A 32% vs B 68% vs C 94% vs D 96%)** 및 **Red–Blue 4단계 탭 시뮬레이터** | • 로컬 L4 GPU 효과(C−B: 성공률 +26%p) 및 Red–Blue 효과(기능 유지율 100%) 입증<br>• Opengrep·OSV·Gitleaks 클린 라이선스 툴팁 제공 |
| **슬라이드 03 & 04: 신고서 & 완료 리포트**<br>(`activeSlide = 2, 3`) | • **슬라이드 03**: 24h(KISA) → 72h(개보위) 신고서 코파일럿 (쉬운 질문 3가지 + 실시간 초안 복사)<br>• **슬라이드 04**: 72시간 완료 리포트(`/api/reports/plain`) & OWASP ZAP 공격 재현(`200 OK` → `400 BLOCKED`) | • 법정 신고 기한(24h/72h) 준수 지원 (`[확인 필요]` 자동 표시)<br>• 백엔드 API 응답 실시간 테스터 내장 |

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

DB는 `.env`의 `DATABASE_URL`로 정합니다. Docker 없이 실행할 때 비워 두면 SQLite, Compose에서는 로컬 PostgreSQL을 씁니다. Supabase 연결 문자열을 넣으면 팀 공용 DB를 사용합니다. 기본 모드의 Item 예제만 자동 생성하며, 실제 서비스 스키마·인증·비동기 큐는 [DB 설계](docs/db-erd.md)와 [활성화 절차](docs/async-llm.md)를 따릅니다.

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
