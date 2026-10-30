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
| MCP Python SDK (`mcp`) | 1.30.0 | 독립 stdio MCP 서버에서 로컬 LLM 수정 제안을 사용자 AI 에이전트에 전달 | MIT | https://github.com/modelcontextprotocol/python-sdk |

## 외부 API

| 명칭 | 용도 | 라이선스·이용약관 | 출처 |
|---|---|---|---|
| Supabase | 팀 공용 PostgreSQL DB 호스팅 | Supabase Terms of Service | https://supabase.com |

## 사전 보유 코드

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| | | | |

## 기타 (AI 도구, 디자인 에셋, 폰트 등)

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| Claude Code (Anthropic) | 백엔드 골격·Docker 개발 환경 코드 작성 보조 | Anthropic 이용약관 | https://claude.com/claude-code |
| Docker Engine · Docker Compose | 개발 환경 컨테이너 실행 | Apache-2.0 (Docker Desktop은 Docker 구독 약관, 개인·교육용 무료) | https://docs.docker.com/compose/ |
| Codex (OpenAI) | 독립 MCP 전달 모듈·테스트·연결 문서 작성 보조 | OpenAI 이용약관 | https://openai.com/codex/ |
