# DB 설계와 적용 계약 (#7)

사용자 결정: **무료 데모 플랜 하나, 한도는 설정값으로 관리, 결제 연동 없음**. 기존 `docs/7-db-design` 설계를 이어 받아 현재 보안엔진(#15), LLM(#20/#29), 비동기 큐(#26)와 맞췄습니다. 실행 SQL은 [db-schema.sql](db-schema.sql)입니다. 팀 리뷰 전에는 공용 Supabase에 적용하지 않습니다.

## ERD

```mermaid
erDiagram
    auth_users ||--|| profile : "가입 시 생성"
    plan ||--o{ profile : "무료 데모"
    profile |o--o{ project : "소유 (익명은 토큰)"
    project ||--o{ scan : "검사 이력"
    scan ||--o{ tool_run : "검사 범위"
    scan ||--o{ finding : "정규화 결과"
    finding ||--o{ explanation : "C 또는 D 설명"
    plan {
        text code PK "demo만"
        int monthly_price "0만"
        int max_projects "null=미설정"
        int max_scans_per_day "null=미설정"
    }
    profile {
        uuid id PK,FK "auth.users.id"
        text plan_code FK
        text display_name
        text avatar_url
    }
    project {
        bigint id PK
        uuid owner_id FK "없으면 claim token 필요"
        text claim_token_hash "SHA256만 저장"
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
        jsonb coverage "registry_used/실패/검사 범위"
    }
    finding {
        bigint id PK
        bigint scan_id FK
        text fingerprint
        text category
        text severity
        text explain_status
        jsonb llm_context "4가지 판정/변화/수정 힌트"
    }
    explanation {
        bigint id PK
        bigint finding_id FK
        text variant "C Blue, D Red-Blue, B 과거 기록"
        text ai_fix_prompt
        text red_verdict
        jsonb red_rounds
        boolean needs_manual_review
        jsonb covers
    }
```

공개 스키마의 핵심 테이블은 **7개**입니다: plan, profile, project, scan, tool_run, finding, explanation. Supabase의 auth.users는 별도이며 #26의 llm_job은 작업 큐용 추가 테이블입니다. 큐 적용 후 총 8개인 것은 정상입니다.

## 플랜과 한도

`plan.code='demo'`, 가격 0원만 허용합니다. 회원가입/기존 사용자 backfill 시 기본 demo 플랜을 연결합니다. 현재 한도 숫자는 합의된 값이 없어 null로 시작합니다. null은 미설정이며 무제한을 뜻합니다. 양수로 바꾸면 신규 접수 API가 해당 값을 읽어 제한해야 합니다. **SQL 설정만으로 일별 접수 횟수가 자동 제한되지는 않습니다.**

예시 설정(숫자는 운영자가 정함):

```sql
update public.plan set max_projects = 3, max_scans_per_day = 10 where code = 'demo';
```

기존 row를 `ON CONFLICT DO NOTHING`으로 유지하므로 SQL 재적용이 운영자 한도 설정을 덮어쓰지 않습니다. 프로젝트당 동시 진행 검사 1개는 scan의 부분 unique index가 별도로 보장합니다. 요금제 결제/업그레이드 UI는 이번 범위가 아닙니다.

## 인증과 접근 경계

- Supabase Auth의 Google/GitHub OAuth를 사용합니다. 이메일·비밀번호는 서비스 테이블에 복사하지 않습니다.
- `auth.users` 삽입 trigger가 profile을 만듭니다. 적용 전 이미 가입한 사용자도 backfill하며 기존 profile 값은 덮어쓰지 않습니다. [Supabase 사용자 데이터 관리](https://supabase.com/docs/guides/auth/managing-user-data)
- 프론트는 access token을 FastAPI의 `Authorization: Bearer ...`에 보냅니다. #26 API가 Auth 서버 검증 후 `project.owner_id`를 확인합니다. 타인 프로젝트와 존재하지 않는 프로젝트는 같은 404를 사용합니다.
- 핵심 7개 테이블에 RLS를 켜고 클라이언트용 정책은 만들지 않습니다. 직접 DB 접속 권한을 가진 백엔드는 **매 요청의 소유권 검사를 반드시 수행**해야 합니다. RLS가 postgres/service-role의 우회를 막지는 않습니다. [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)
- 익명 프로젝트는 owner 없이 claim_token_hash로만 식별할 수 있는 구조를 유지합니다. 토큰 생성/claim API는 별도 구현 대상이며, #26은 로그인된 소유자의 LLM 작업만 허용합니다. 익명 사용자에게 GPU/리포트를 공개하는 우회 경로를 만들지 않습니다.
- 사용자 삭제 시 profile → project → scan → finding → explanation이 연쇄 삭제됩니다. claim token 원문·OAuth secret·GPU 키는 Git/브라우저 공개 변수에 넣지 않습니다.

OAuth 설정은 Supabase Authentication → Providers에서 하고 callback은 Supabase가 제공하는 URL을 사용합니다. 브라우저 return URL은 실제 프론트 주소를 허용 목록에 등록합니다. Cloudflare 임시 호스트가 바뀌면 이 목록도 갱신해야 합니다. 실제 provider secret이나 Supabase 프로젝트를 이 PR에서 생성/변경하지 않습니다.

## 엔진 → DB → LLM 계약

| 엔진 항목 | DB 저장 |
|---|---|
| `target.commit_sha`, summary | scan.commit_sha, scan.summary |
| `coverage`의 각 항목 | tool_run.coverage에 전체 보관. ok→done, error→failed, skipped/no_target/not_installed→skipped |
| `osv`, `semgrep`, `gitleaks`, `config` | tool명 그대로 저장. 과거 osv-scanner/opengrep도 허용 |
| category=config, severity=unknown | 그대로 저장 가능. 임의로 high/low로 바꾸지 않음 |
| fingerprint, location, package, references | finding의 대응 컬럼/refs |
| status/change/flags/fix_hint/what/context | finding.llm_context의 같은 키. 원본 엔진 구조 대신 LLM adapter 규격 사용 |
| Blue(C)/Red–Blue(D) | explanation.variant. B는 과거 데이터 보존용 |
| red_verdict/red_rounds/needs_manual_review/covers | explanation에 보존. 검토되지 않은 기존 설명의 기본 manual_review=true |

스캐너가 마스킹한 데이터만 저장합니다. `finding.raw`는 마스킹된 원본이고, LLM 입력에 raw 전체를 넘기지 않습니다. 패키지 묶음은 #29의 adapter가 만든 대표 finding/covers와 검사 커밋을 함께 연결해야 합니다. Red pass가 실제 취약점 수정 완료라는 뜻은 아닙니다.

#26 worker가 사용할 때는 모든 finding 저장과 `scan.status='explaining'` 전환을 한 transaction으로 커밋합니다. 그 이후 입력은 불변이며 재검사는 새 scan입니다. #26은 pending/done/failed/skipped와 explanation을 함께 저장합니다. 모든 항목이 terminal인 scan의 done은 검사/해석 종료이며, 문제가 없거나 모든 해석이 성공했다는 뜻이 아닙니다.

## 적용과 업그레이드

1. 담당자가 대상 Supabase 프로젝트와 백업을 확인합니다. SQL은 PostgreSQL/Supabase용이며 SQLite에 실행하지 않습니다.
2. SQL Editor에서 `docs/db-schema.sql`을 실행합니다. 전체가 transaction이며 기존 6-table 초안에도 적용 가능합니다. 기존 데이터는 삭제하지 않고 컬럼·허용 상태를 확장합니다.
3. Schema Visualizer에서 핵심 7개 테이블과 RLS를 확인합니다. `plan`의 demo 설정과 기존/신규 사용자 profile 연결을 확인합니다.
4. #26을 사용할 경우 그 PR의 `docs/migrations/026-async-llm.sql`을 이어서 적용합니다. 중복 컬럼/상태 확장은 재적용 가능하고 llm_job을 추가합니다.
5. #26의 인증/소유권/큐 검증을 마친 다음 서버 feature flag와 프록시를 함께 전환합니다.

이 저장소가 Supabase를 사용할 서비스입니다. 로컬 개발은 루트 `.env`, 일반 서버는 권한 600인 `~/.config/72hours/backend.env`에 다음 연결 설정을 둡니다. 기존 LLM/GPU 설정은 유지합니다.

```dotenv
# Supabase Connect > Session pooler URI, 비밀번호의 특수문자는 URL 인코딩
DATABASE_URL=postgresql://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=PROJECT_PUBLISHABLE_KEY
# 스키마·인증·프록시 준비 후에 활성화
LLM_JOBS_ENABLED=true
```

DB URI와 Auth URL은 반드시 같은 프로젝트를 가리켜야 합니다. 위 값은 예시이며 실제 프로젝트나 키를 생성한 것이 아닙니다. 프론트에는 Supabase URL/publishable key만 전달하고 DB 비밀번호/service-role/GPU 키는 전달하지 않습니다. 기존 시연 서버의 SQLite를 자동 이전하거나 서버 환경 파일을 덮어쓰지 않습니다. 큐 worker와 Bearer 프록시 구성은 [비동기 연결 문서](async-llm.md)의 활성화 절차를 따릅니다.

**서비스 테이블의 기준은 SQL**입니다. SQLModel `create_all`로 production 스키마를 만들지 않습니다. 현재 기본 서버의 Item/SQLite 예제는 유지하며, #26 opt-in 모드는 startup DDL을 실행하지 않습니다. SQLite는 이 스키마의 동등한 대체물이 아닙니다. DB 기능 테스트는 일회용 PostgreSQL에서 수행합니다.

재적용은 알려진 #7 초안 업그레이드 범위에서 검증합니다. 임의의 다른 테이블 구조를 자동 수리하지 않으며, 제약 이름/타입이 다르면 transaction이 실패하게 두고 담당자가 migration을 작성합니다. 데이터가 있는 상태에서 `DROP TABLE` 또는 역방향 스키마 초기화를 하지 않습니다.

## 검증

```bash
pip install -r backend/requirements-dev.txt
DB_SCHEMA_TEST_URL=postgresql://postgres@127.0.0.1:5432/postgres \
  python -m pytest tests/db -q
```

테스트는 loopback PostgreSQL에 무작위 이름의 **새 DB만** 생성·삭제합니다. 신규 설치/기존 초안 업그레이드, 반복 적용, RLS, 회원가입/backfill, 설정 보존, 중복 검사 방지, 엔진/Red–Blue 필드 저장과 cascade를 확인합니다. 테스트의 auth.users는 최소 구조의 대역이며 실제 OAuth 로그인 검증을 대신하지 않습니다. CI도 일회용 Postgres 17을 사용합니다.
