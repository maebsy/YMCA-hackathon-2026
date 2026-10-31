# 외부 자원 활용 내역 (ⓕ)

> **대회 규정: 여기 적지 않은 외부 자원을 쓴 사실이 확인되면 실격입니다.**
> 라이브러리·모델·데이터셋·API를 추가하는 **그 PR에서** 이 표도 같이 고치세요.
> 제출 직전에 이 표를 공식 제출 양식으로 옮깁니다.

## 오픈소스 (라이브러리·프레임워크·모델·데이터셋)

| 명칭 | 버전 | 용도 | 라이선스 | 출처 |
|---|---|---|---|---|
| FastAPI | 0.162.0 | 백엔드 API 서버 | MIT | https://github.com/fastapi/fastapi |
| Caddy | 2.11.7 | 일반 서버의 웹·API 프록시, 공개 시연 HTTPS 및 접근 인증 | Apache-2.0 | https://github.com/caddyserver/caddy |
| cloudflared | 2026.10.7 | 승인된 시연용 HTTPS 터널 클라이언트, 공식 SHA-256 고정 검증 | Apache-2.0 | https://github.com/cloudflare/cloudflared |
| Node.js | 24.19.0 | 별도 담당자가 구현할 프론트엔드의 서버 실행 환경 | MIT 및 포함 구성요소별 라이선스 | https://nodejs.org/ |
| Next.js | 16.4.3 | 프론트엔드 웹 대시보드 및 SSR/App Router 프레임워크 | MIT | https://github.com/vercel/next.js |
| React & React-DOM | 19.3.0 | 사용자 인터페이스 렌더링 및 상태 관리 라이브러리 | MIT | https://github.com/facebook/react |
| Tailwind CSS | 4.x | 대시보드 반응형 유틸리티 디자인 스타일링 | MIT | https://github.com/tailwindlabs/tailwindcss |
| Lucide React | 1.65.0 | 보안 대시보드 아이콘 컴포넌트 라이브러리 | ISC | https://github.com/lucide-icons/lucide |
| Google Fonts (IBM Plex Sans KR, JetBrains Mono) | 최신 | 웹 대시보드 본문 한글 폰트 및 개발자 터미널 고정폭 폰트 | OFL-1.1 / Apache-2.0 | https://fonts.google.com |
| Uvicorn | 0.54.0 | 백엔드 실행 서버 | BSD-3-Clause | https://github.com/encode/uvicorn |
| SQLModel | 0.0.48 | DB 테이블 정의·조회 | MIT | https://github.com/fastapi/sqlmodel |
| SQLAlchemy | 2.1.6 | DB 연결 (SQLModel 기반) | MIT | https://github.com/sqlalchemy/sqlalchemy |
| psycopg | 3.3.6 | PostgreSQL(Supabase) 드라이버 | LGPL-3.0 | https://github.com/psycopg/psycopg |
| pydantic-settings | 2.16.2 | `.env` 설정 읽기 | MIT | https://github.com/pydantic/pydantic-settings |
| Python 공식 Docker 이미지 | 3.12-slim | 백엔드 컨테이너 기반 이미지 | PSF-2.0 (포함된 Debian 패키지는 각 라이선스) | https://hub.docker.com/_/python |
| PostgreSQL 공식 Docker 이미지 | 17-alpine | 로컬 개발용 DB | PostgreSQL License | https://hub.docker.com/_/postgres |
| PostgreSQL Windows 바이너리 | 17.11-5 | #7 스키마/RLS·#26 큐의 독립 임시 DB 통합 테스트 (서비스 등록 없음) | PostgreSQL License | https://www.enterprisedb.com/download-postgresql-binaries |
| HTTPX | 0.28.1 | LLM 서버(vLLM) 호출 | BSD-3-Clause | https://github.com/encode/httpx |
| pytest | 9.2.0 | 백엔드·보안엔진 테스트 (개발용) | MIT | https://github.com/pytest-dev/pytest |
| vLLM | 0.32.0 | GPU 서버 LLM 서빙 (OpenAI 호환 API) | Apache-2.0 | https://github.com/vllm-project/vllm |
| Qwen3.8-27B (모델) | 2026-08 공개본 | Blue·Red 해석 LLM의 원본 모델 | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.8-27B |
| Qwen3.8-27B AWQ INT4 (양자화 체크포인트) | 커밋 5a2ee524cbc9 | L4 24GB에 올리기 위한 4비트 모델 | Apache-2.0 | https://huggingface.co/avyukth/Qwen3.8-27B-AWQ-INT4 |
| uv | 0.13.6 (GPU 서버) | GPU 서버 파이썬 환경 설치, Python 3.12.16 관리 | Apache-2.0 / MIT | https://github.com/astral-sh/uv |
| OSV-Scanner | 2.7.0 | 보안엔진: 외부 부품(의존성) 취약점 검사 | Apache-2.0 | https://github.com/google/osv-scanner |
| Opengrep | 1.33.1 | 보안엔진: 코드 정적 분석 (기본 코드 검사기, Semgrep CE 호환 포크) | LGPL-2.1 | https://github.com/opengrep/opengrep |
| Semgrep Community Edition | 1.183.0 | 보안엔진: 코드 정적 분석 (Opengrep이 없을 때 대체) | LGPL-2.1 | https://github.com/semgrep/semgrep |
| Semgrep Registry 룰셋 `p/default` | 실행 시점 최신 | 보안엔진: **내부 비교·검증용만** (기본 꺼짐, `--with-registry p/default`일 때만). 서비스 결과에는 사용 안 함 | Semgrep Rules License v1.0 (내부 사용 한정, 경쟁 제품·SaaS 사용 불가) | https://semgrep.dev/p/default |
| Gitleaks | 8.30.1 | 보안엔진: 코드 속 비밀값(API 키 등) 노출 검사 | MIT | https://github.com/gitleaks/gitleaks |
| jsonschema | 4.26.0 | 보안엔진 출력 규격 검증 테스트 (개발용) | MIT | https://github.com/python-jsonschema/jsonschema |
| OWASP NodeGoat | c5cb68a7084e4ae7dcc60e6a98768720a81841e8 | 공개 취약 앱 소스의 스캐너·OSV 온라인·마스킹 검증 (앱 실행 없음) | Apache-2.0 | https://github.com/OWASP/NodeGoat |
| CERT/CC SSVC 결정표 (CISA Coordinator v2.0.3) | 커밋 c5be80f180f0 | 위험도 해석의 결정표 (`backend/app/llm/data/` 사본) | MIT (SEI) 계열, 전문은 `backend/app/llm/data/SSVC-LICENSE.txt` | https://github.com/CERTCC/SSVC |
| OpenVEX 명세 (용어만 사용) | v0.2.0 | 문맥 분석 결과의 상태·사유 용어 | CC0-1.0 | https://github.com/openvex/spec |
| MCP Python SDK (`mcp`) | 1.30.0 | 독립 stdio MCP 서버에서 로컬 LLM 수정 제안을 사용자 AI 에이전트에 전달 | MIT | https://github.com/modelcontextprotocol/python-sdk |

## 외부 API

| 명칭 | 용도 | 라이선스·이용약관 | 출처 |
|---|---|---|---|
| Supabase | 팀 공용 PostgreSQL DB 호스팅, 로그인·Auth 서버의 access token 검증 (#7/#26) | Supabase Terms of Service | https://supabase.com |
| Cloudflare Quick Tunnels | 공인 IP 없이 일반 서버의 시연 웹/API를 임시 HTTPS 주소로 공개 | Cloudflare 이용약관 | https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/ |
| Hugging Face Hub | 모델 내려받기 (가중치는 GPU 서버에서만 실행) | Hugging Face Terms of Service | https://huggingface.co |
| Google OAuth (Google Identity) | Google 계정으로 가입·로그인 | Google APIs Terms of Service | https://developers.google.com/identity |
| GitHub OAuth Apps | GitHub 계정으로 가입·로그인 | GitHub Terms of Service | https://docs.github.com/apps/oauth-apps |
| OSV.dev API (api.osv.dev) | OSV-Scanner가 취약점 DB 조회 (무료, 키 없음) | OSV.dev 이용약관, 데이터는 출처(GitHub Advisory 등)별 라이선스 — 제출 전 확인 | https://osv.dev |
| Semgrep Registry (semgrep.dev) | 내부 비교용 `p/default` 룰셋 다운로드 (기본 꺼짐) | Semgrep Rules License v1.0 | https://docs.semgrep.dev/licensing |
| GitHub (공개 저장소 clone) | 검사 대상 사이트 소스 코드 받기 (공개 저장소만, 소스 분석만) | GitHub 이용약관 | https://github.com |
| CISA KEV 카탈로그 | 실제 공격에 쓰인 취약점 목록 조회 (위험도 해석) | 미국 정부 공개 자료 | https://www.cisa.gov/known-exploited-vulnerabilities-catalog |
| FIRST EPSS API | CVE별 30일 내 악용 확률 조회 (위험도 해석) | 무료 공개, 등록 불필요 | https://www.first.org/epss/api |

## 사전 보유 코드

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| | | | |

## 기타 (AI 도구, 디자인 에셋, 폰트 등)

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| Claude Code (Anthropic) | 백엔드 골격·Docker 개발 환경·LLM 해석 모듈·리포트와 신고서 초안 코드 작성 보조 | Anthropic 이용약관 | https://claude.com/claude-code |
| Codex (OpenAI) | 일반 서버·독립 MCP·비동기 LLM 큐·인증 경계·DB 스키마와 테스트·연결 문서 작성 및 PR 병합 오류 수정 보조 | OpenAI 이용약관 | https://openai.com/codex/ |
| Docker Engine · Docker Compose | 개발 환경 컨테이너 실행 | Apache-2.0 (Docker Desktop은 Docker 구독 약관, 개인·교육용 무료) | https://docs.docker.com/compose/ |
| Claude (Anthropic) | 보안엔진(`security_engine/`) 설계·코드·Semgrep 규칙 작성 보조 | Anthropic 이용약관 | https://claude.ai |
