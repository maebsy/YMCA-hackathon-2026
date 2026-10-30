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
| OSV-Scanner | 2.7.0 | 보안엔진: 외부 부품(의존성) 취약점 검사 | Apache-2.0 | https://github.com/google/osv-scanner |
| Opengrep | 1.33.1 | 보안엔진: 코드 정적 분석 (기본 코드 검사기, Semgrep CE 호환 포크) | LGPL-2.1 | https://github.com/opengrep/opengrep |
| Semgrep Community Edition | 1.183.0 | 보안엔진: 코드 정적 분석 (Opengrep이 없을 때 대체) | LGPL-2.1 | https://github.com/semgrep/semgrep |
| Semgrep Registry 룰셋 `p/default` | 실행 시점 최신 | 보안엔진: **내부 비교·검증용만** (기본 꺼짐, `--with-registry p/default`일 때만). 서비스 결과에는 사용 안 함 | Semgrep Rules License v1.0 (내부 사용 한정, 경쟁 제품·SaaS 사용 불가) | https://semgrep.dev/p/default |
| Gitleaks | 8.30.1 | 보안엔진: 코드 속 비밀값(API 키 등) 노출 검사 | MIT | https://github.com/gitleaks/gitleaks |
| pytest | 9.x | 보안엔진 테스트 (개발용) | MIT | https://github.com/pytest-dev/pytest |
| jsonschema | 4.x | 보안엔진 출력 규격 검증 테스트 (개발용) | MIT | https://github.com/python-jsonschema/jsonschema |

## 외부 API

| 명칭 | 용도 | 라이선스·이용약관 | 출처 |
|---|---|---|---|
| Supabase | 팀 공용 PostgreSQL DB 호스팅 | Supabase Terms of Service | https://supabase.com |
| OSV.dev API (api.osv.dev) | OSV-Scanner가 취약점 DB 조회 (무료, 키 없음) | OSV.dev 이용약관, 데이터는 출처(GitHub Advisory 등)별 라이선스 — 제출 전 확인 | https://osv.dev |
| Semgrep Registry (semgrep.dev) | 내부 비교용 `p/default` 룰셋 다운로드 (기본 꺼짐) | Semgrep Rules License v1.0 | https://docs.semgrep.dev/licensing |
| GitHub (공개 저장소 clone) | 검사 대상 사이트 소스 코드 받기 (공개 저장소만, 소스 분석만) | GitHub 이용약관 | https://github.com |

## 사전 보유 코드

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| | | | |

## 기타 (AI 도구, 디자인 에셋, 폰트 등)

| 명칭 | 용도 | 라이선스 | 출처 |
|---|---|---|---|
| Claude Code (Anthropic) | 백엔드 골격 코드 작성 보조 | Anthropic 이용약관 | https://claude.com/claude-code |
| Claude (Anthropic) | 보안엔진(`security_engine/`) 설계·코드·Semgrep 규칙 작성 보조 | Anthropic 이용약관 | https://claude.ai |
