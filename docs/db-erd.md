# 데이터 저장 구조와 Supabase 적용

현재 웹의 공개 검사 흐름은 로그인 없이 사용할 수 있는 데모 경로입니다. Supabase를 사용하는 사용자별 저장·인증·LLM worker도 구현되어 있지만 **별도 설정과 클라이언트 연결이 필요한 선택 구성**입니다. SQL 파일이 있다는 이유만으로 공개 서버에 해당 구성이 적용됐다고 판단하면 안 됩니다.

## 구성별 저장 범위

| 구성 | 저장·인증 동작 |
|---|---|
| 기본 설정: `DATABASE_URL` 없음, 두 인증 플래그 `false` | `backend/app.db`의 SQLite `scan_job`에 검사 응답 저장. 로그인 불필요 |
| PostgreSQL 연결, 두 인증 플래그 `false` | `scan_job`과 서비스 관계 테이블에 익명 검사 저장. 스키마를 먼저 적용해야 함 |
| `SCAN_REQUIRE_AUTH=true` | 검사 접수·조회에 Supabase Bearer 인증 추가. LLM worker를 켜는 설정은 아님 |
| `LLM_JOBS_ENABLED=true` | PostgreSQL 필수. 검사와 저장된 finding의 LLM 작업에 Supabase 인증 적용. 별도 worker 필요 |

기본 LLM `/api/llm/explain/tasks`는 **API 메모리에 저장**되므로 검사 응답의 DB 저장과 수명이 다릅니다. PostgreSQL을 연결하는 것만으로 LLM 결과가 영속화되지는 않습니다. [LLM 작업 모드와 전환 조건](async-llm.md), [검사 저장 계약](scan-persistence.md)을 함께 확인하세요.

## PostgreSQL ERD

```mermaid
erDiagram
    auth_users ||--|| profile : "가입 시 생성"
    plan ||--o{ profile : "무료 데모"
    profile |o--o{ project : "소유자 또는 익명"
    project ||--o{ scan : "검사 이력"
    scan ||--o{ tool_run : "도구 실행 범위"
    scan ||--o{ finding : "정규화 결과"
    finding ||--o{ explanation : "LLM 설명"
    finding ||--o| llm_job : "선택형 작업 큐"
    profile |o--o{ scan_job : "접수 소유자"
    scan |o--o| scan_job : "완료 응답"
    plan {
        text code PK "demo"
        int monthly_price "0"
        int max_projects "null=미설정"
        int max_scans_per_day "null=미설정"
    }
    profile {
        uuid id PK,FK "auth.users.id"
        text plan_code FK
    }
    project {
        bigint id PK
        uuid owner_id FK "익명은 null"
        text claim_token_hash "익명 job ID의 SHA256"
        text repo_url
    }
    scan {
        bigint id PK
        bigint project_id FK
        text status
        text commit_sha
        jsonb summary
    }
    tool_run {
        bigint id PK
        bigint scan_id FK
        text tool
        text status
        jsonb coverage
    }
    finding {
        bigint id PK
        bigint scan_id FK
        text fingerprint
        text explain_status
        jsonb llm_context
    }
    explanation {
        bigint id PK
        bigint finding_id FK
        text variant "C Blue, D Red-Blue"
        text ai_fix_prompt
        text red_verdict
        jsonb red_rounds
        boolean needs_manual_review
        jsonb covers
    }
    llm_job {
        uuid id PK
        bigint finding_id FK,UK
        text status
        uuid lease_token
    }
    scan_job {
        varchar id PK "API job ID"
        uuid owner_id FK
        bigint scan_id FK,UK "db_scan_id"
        text status
        jsonb result
    }
```

핵심 7개 테이블에 검사 접수용 `scan_job`을 더하면 8개, 선택형 LLM 큐 `llm_job`까지 적용하면 9개입니다. Supabase `auth.users`와 개발용 `Item` 테이블은 이 수에 포함하지 않습니다. SQLite는 `scan_job` 응답 저장만 제공하며 위 관계 모델의 대체물이 아닙니다.

## 인증·플랜의 구현 범위

- Supabase Auth 사용자 삽입 trigger와 기존 사용자 backfill이 `profile`을 만들고 무료 `demo` 플랜을 연결합니다. 이메일·비밀번호를 서비스 테이블에 복사하지 않습니다.
- 인증 모드의 API는 Supabase 사용자 조회로 검증한 UUID를 소유권 검사에 사용합니다. 다른 소유자의 데이터와 없는 데이터는 동일하게 404를 반환합니다. 현재 공개 웹의 로그인 없는 흐름에 이 모드가 자동 연결되지는 않습니다.
- 서비스 테이블에는 RLS와 클라이언트 역할 권한 제한을 적용합니다. DB 권한이 높은 백엔드는 RLS를 우회할 수 있으므로 API의 소유권 검사가 필요합니다. 프론트에서 서비스 테이블을 직접 조회하는 정책은 제공하지 않습니다.
- 익명 검사는 `job_id`를 가진 사용자가 결과를 읽는 방식입니다. PostgreSQL 프로젝트에는 그 ID의 해시를 저장합니다. 계정으로 이전하는 claim API는 없으며, 공개 데모의 검사·리포트가 회원 전용이라는 뜻도 아닙니다.
- `plan`의 가격은 0이며 결제 연동은 없습니다. `max_projects`, `max_scans_per_day`는 기본 `null`입니다. **현재 API는 이 값을 읽어 한도를 집행하지 않습니다.** SQL 값만 바꿔도 사용량이 제한된다고 안내하면 안 됩니다.
- 프로젝트별 진행 검사 1개를 허용하는 DB 인덱스가 있지만, 현재 저장 경로는 검사마다 새 `project`를 만듭니다. 이 인덱스는 같은 GitHub 저장소의 중복 접수를 막는 장치가 아닙니다.

## 엔진 → DB → LLM

| 입력 | 저장 계약 |
|---|---|
| 검사 커밋, 요약 | `scan.commit_sha`, `scan.summary` |
| 도구별 버전·상태·검사 범위 | `tool_run`과 전체 `coverage`. `ok→done`, `error→failed`, 나머지 비실행 상태는 `skipped` |
| 모든 정규화 finding | 위치·패키지·참조·마스킹된 원본을 보존. 미리보기 상위 50건 제한과 무관 |
| LLM 보충 입력 | 현재 저장 경로는 `what`, `flags`, `fix_hint`, `status`, `change`를 `finding.llm_context`에 기록 |
| worker의 Red–Blue 결과 | `explanation` 및 `finding.explain_status`. 스키마는 기존 B/C 기록도 보존 |

스캐너가 이미 마스킹한 결과를 저장하며, `finding.raw` 전체를 LLM에 넘기지 않습니다. `severity=unknown`이나 도구 미실행을 임의로 성공·저위험으로 바꾸지 않습니다. worker 큐 단위는 DB finding 1개이며, 공개 미리보기의 패키지 묶음과 동일한 저장 계약은 아닙니다. Red pass나 `scan.status=done`은 취약점 수정 완료를 뜻하지 않습니다.

## 스키마 적용 순서

SQL의 실행 대상은 PostgreSQL/Supabase입니다. **`auth.users`가 먼저 존재해야 하므로 일반 PostgreSQL 컨테이너만 띄워 바로 적용할 수는 없습니다.** 테스트의 Auth 대역을 운영에 설치하는 방식도 지원하지 않습니다.

1. 대상 Supabase 프로젝트, 백업, 기존 스키마를 확인합니다.
2. [`db-schema.sql`](db-schema.sql): 핵심 7개 테이블, trigger, RLS와 기존 초안 업그레이드.
3. LLM worker를 사용할 경우 [`026-async-llm.sql`](migrations/026-async-llm.sql): `llm_job` 추가.
4. [`052-scan-persistence.sql`](migrations/052-scan-persistence.sql): 검사 접수·응답 `scan_job` 추가.
5. 같은 프로젝트의 DB·Auth 설정으로 인증 및 저장을 검증합니다. LLM 모드의 실행 조건은 [별도 절차](async-llm.md#활성화-절차)를 따릅니다.

로컬은 저장소 루트 `.env`, 서버는 배포 구성의 비공개 환경 파일에 설정합니다. 다음은 연결 형식 예시입니다.

```dotenv
# 비밀번호 특수문자는 URL 인코딩. 실제 연결 주소는 Supabase Connect에서 확인
DATABASE_URL=postgresql://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=PROJECT_PUBLISHABLE_KEY
# 아래 값은 기본 모드를 유지함. 인증 모드의 실행 조건은 async-llm.md 참조
SCAN_REQUIRE_AUTH=false
LLM_JOBS_ENABLED=false
```

DB URI와 Auth URL은 같은 프로젝트여야 합니다. DB 비밀번호·service-role·GPU 키는 브라우저에 전달하지 않습니다. SQLite 자료의 자동 이전은 없습니다. 서비스 스키마는 위 SQL로 관리하며 앱 시작 시 자동 migration하지 않습니다. 기본 모드의 SQLModel 초기화는 개발용 `Item`, SQLite 검사 저장 초기화는 `scan_job`에만 해당합니다.

## 검증

저장소 루트에서 실행합니다. Bash/Git Bash 예시이며, 연결 주소는 본인 PC의 일회용 PostgreSQL로 지정합니다.

```bash
python -m pip install -r backend/requirements-dev.txt
DB_SCHEMA_TEST_URL=postgresql://postgres@127.0.0.1:5432/postgres \
  python -m pytest tests/db -q
```

테스트는 loopback 서버에 무작위 이름의 새 DB를 생성·삭제해 신규 설치, 알려진 초안 업그레이드, 반복 적용, RLS, profile 생성과 cascade를 확인합니다. 임의 스키마를 자동 수리하거나 실제 Supabase OAuth를 검증하는 테스트는 아닙니다. 인증·큐·검사 저장 테스트는 [LLM 문서](async-llm.md#검증)와 [검사 저장 문서](scan-persistence.md#검증)를 참고하세요.

구현 기준: [앱 초기화](../backend/app/main.py), [설정](../backend/app/explain_jobs/config.py), [검사 저장](../backend/app/scan_store.py), [큐 저장](../backend/app/explain_jobs/store.py).
