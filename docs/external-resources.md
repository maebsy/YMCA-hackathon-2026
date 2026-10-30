# 외부 자원 활용 내역 (ⓕ)

> **대회 규정: 여기 적지 않은 외부 자원을 쓴 사실이 확인되면 실격입니다.**
> 라이브러리·모델·데이터셋·API를 추가하는 **그 PR에서** 이 표도 같이 고치세요.
> 제출 직전에 이 표를 공식 제출 양식으로 옮깁니다.

## 오픈소스 (라이브러리·프레임워크·모델·데이터셋)

| 명칭 | 버전 | 용도 | 라이선스 | 출처 |
|---|---|---|---|---|
| FastAPI | 0.162.0 | 백엔드 API 서버 | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | 0.54.0 | 백엔드 실행 서버 | BSD-3-Clause | https://github.com/encode/uvicorn |
| SQLModel | 0.0.48 | DB 테이블 정의·조회 | MIT | https://github.com/fastapi/sqlmodel |
| SQLAlchemy | 2.1.6 | DB 연결 (SQLModel 기반) | MIT | https://github.com/sqlalchemy/sqlalchemy |
| psycopg | 3.3.6 | PostgreSQL(Supabase) 드라이버 | LGPL-3.0 | https://github.com/psycopg/psycopg |
| pydantic-settings | 2.16.2 | `.env` 설정 읽기 | MIT | https://github.com/pydantic/pydantic-settings |
| Python 공식 Docker 이미지 | 3.12-slim | 백엔드 컨테이너 기반 이미지 | PSF-2.0 (포함된 Debian 패키지는 각 라이선스) | https://hub.docker.com/_/python |
| PostgreSQL 공식 Docker 이미지 | 17-alpine | 로컬 개발용 DB | PostgreSQL License | https://hub.docker.com/_/postgres |
| HTTPX | 0.28.1 | LLM 서버(vLLM) 호출 | BSD-3-Clause | https://github.com/encode/httpx |
| pytest | 9.2.0 | 백엔드 테스트 (개발용) | MIT | https://github.com/pytest-dev/pytest |
| vLLM | 0.32.0 | GPU 서버 LLM 서빙 (OpenAI 호환 API) | Apache-2.0 | https://github.com/vllm-project/vllm |
| Qwen3.8-27B (모델) | 2026-08 공개본 | Blue·Red 해석 LLM의 원본 모델 | Apache-2.0 | https://huggingface.co/Qwen/Qwen3.8-27B |
| Qwen3.8-27B AWQ INT4 (양자화 체크포인트) | 커밋 5a2ee524cbc9 | L4 24GB에 올리기 위한 4비트 모델 | Apache-2.0 | https://huggingface.co/avyukth/Qwen3.8-27B-AWQ-INT4 |
| uv | 0.13.6 (GPU 서버) | GPU 서버 파이썬 환경 설치, Python 3.12.16 관리 | Apache-2.0 / MIT | https://github.com/astral-sh/uv |

## 외부 API

| 명칭 | 용도 | 라이선스·이용약관 | 출처 |
|---|---|---|---|
| Supabase | 팀 공용 PostgreSQL DB 호스팅 | Supabase Terms of Service | https://supabase.com |
| Hugging Face Hub | 모델 내려받기 (가중치는 GPU 서버에서만 실행) | Hugging Face Terms of Service | https://huggingface.co |

## 사전 보유 코드

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| | | | |

## 기타 (AI 도구, 디자인 에셋, 폰트 등)

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| Claude Code (Anthropic) | 백엔드 골격·Docker 개발 환경·LLM 해석 모듈·리포트와 신고서 초안 코드 작성 보조 | Anthropic 이용약관 | https://claude.com/claude-code |
| Docker Engine · Docker Compose | 개발 환경 컨테이너 실행 | Apache-2.0 (Docker Desktop은 Docker 구독 약관, 개인·교육용 무료) | https://docs.docker.com/compose/ |
