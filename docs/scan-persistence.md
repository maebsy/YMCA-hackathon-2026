# 검사 접수와 결과 저장

`POST /api/scans`는 DB에 작업을 접수한 뒤 202를 반환합니다. 검사 완료 시 전체 엔진 JSON과 API 응답을 `scan_job`에 저장하므로 같은 DB를 사용하면 API 재시작 후에도 같은 `job_id`로 완료 결과를 조회할 수 있습니다. **검사 결과 저장과 기본 LLM 미리보기의 메모리 보관은 별개**입니다. [LLM 작업 모드](async-llm.md)를 참고하세요.

## DB 준비

| DB 구성 | 저장 범위·준비 |
|---|---|
| SQLite 기본 데모 | `scan_job` 자동 생성, 검사 응답 snapshot 저장. 서비스 관계 테이블과 DB LLM worker는 없음 |
| PostgreSQL/Supabase | `project`, `scan`, `tool_run`, 모든 `finding`, `scan_job` 저장. SQL 사전 적용 필수 |

PostgreSQL 적용 순서는 [기본 스키마](db-schema.sql) → [LLM 큐 migration](migrations/026-async-llm.sql)(worker 사용 시) → [검사 저장 migration](migrations/052-scan-persistence.sql)입니다. `auth.users` 등 선행 조건과 인증 설정은 [데이터 저장 구조](db-erd.md#스키마-적용-순서)를 따릅니다. 앱이 서비스 관계 스키마를 자동 생성하거나 SQLite 데이터를 PostgreSQL로 옮기지는 않습니다.

## API 식별자와 상태

| 식별자 | 형식·용도 |
|---|---|
| 접수 `job_id` | 32자리 UUID hex. `GET /api/scans/{job_id}`에 사용 |
| 엔진 `scan_id` | 엔진 결과의 문자열 UUID. 재검사 `previous` 조회 키 |
| `db_scan_id` | PostgreSQL 완료 응답에 추가되는 bigint. DB worker 설명 API에 사용 |

외부 조회의 작업 상태는 `queued → running → done | failed`입니다. 응답 내부 엔진 상태는 별도로 `complete | partial | failed`이며, 도구 일부가 실패한 `partial` 결과도 작업 자체는 `done`으로 끝날 수 있습니다. 완료 여부와 검사 범위·취약점 유무를 구분해 표시해야 합니다.

## 저장 계약

- PostgreSQL에서는 관계 데이터와 응답 snapshot을 한 transaction으로 저장합니다. 중간 실패 시 전부 롤백하고 완료 저장을 재호출해도 중복 삽입하거나 완료 결과를 덮어쓰지 않습니다.
- API의 LLM 미리보기 상위 50건 제한과 무관하게 **모든 finding**의 위치·패키지·전체 참조·마스킹된 원본을 보관합니다. 도구 원본 `raw`가 없어도 정규화 finding 전체가 `finding.raw`에 남습니다.
- LLM 입력 한도를 넘는 긴 제목·경로·수정안도 엔진 원본은 저장합니다. 미리보기에서 제외한 항목은 `preview_errors`의 `LLM_INPUT_INVALID`로 표시하고, DB worker 입력 오류는 해당 finding의 실패로 처리합니다.
- 일시적인 DB 연결·트랜잭션 오류는 계산된 결과를 유지한 채 1초·2초 후 **저장만** 재시도합니다(최대 3회). 검사 도구를 재실행하지 않습니다. 입력 검증·무결성 오류는 재시도하지 않습니다.
- 소유자와 finding이 있는 PostgreSQL scan은 관계 테이블에서 `explaining`으로 저장합니다. 익명·발견 0건은 `done`, 엔진 전체 실패는 `failed`입니다. 이는 저장 경로의 판정으로, `SCAN_REQUIRE_AUTH=true`만 켜고 worker를 실행하지 않아도 `explaining`이 될 수 있습니다. 실제 LLM 실행 여부는 `llm_job`과 worker를 확인해야 합니다.

## 인증과 재검사

`LLM_JOBS_ENABLED=true` **또는** `SCAN_REQUIRE_AUTH=true`이면 접수·조회 모두 검증된 Supabase Bearer 인증을 요구합니다. 인증을 먼저 확인한 뒤 DB 스키마를 확인하며, 타인 결과와 없는 결과는 동일하게 404를 반환합니다. `SCAN_ALLOWED_OWNERS`는 검사 가능한 GitHub 소유자를 제한하고, 로그인된 `SCAN_ADMIN_USER_IDS`는 이 제한을 우회할 수 있습니다. 이는 대상 허용 목록이며 데이터 소유권 검사를 대신하지 않습니다.

두 플래그가 모두 `false`이면 추측하기 어려운 `job_id`를 가진 사람이 익명 결과를 읽을 수 있습니다. 인증된 소유자의 결과는 익명으로 조회할 수 없습니다. 익명 결과를 공유할 때는 ID 자체가 접근 수단임을 고려해야 합니다.

재검사 `previous`에는 기존 엔진 `result` 전체 또는 다음 객체를 보냅니다.

```json
{"scan_id": "이전 엔진 UUID"}
```

서버는 ID만 조회 키로 사용하며 **동일 저장소·소유자의 DB 저장본**으로 비교합니다. 클라이언트가 수정한 finding·코드·날짜는 비교 근거로 쓰지 않습니다. 저장본이 없거나 소유자·저장소가 다르면 접수 전에 404 `PREVIOUS_SCAN_NOT_FOUND`를 반환합니다. 익명 결과의 엔진 UUID 역시 재검사 접근 수단으로 취급합니다.

## 중단·장애 동작

실행 중에는 30초마다 120초 lease를 갱신합니다. 정상 종료 시 최대 10초 동안 작업을 기다린 뒤 남은 작업을 취소하고 실패를 기록합니다. 동기 스캐너 thread의 즉시 종료는 보장하지 않지만 취소된 작업이 결과를 뒤늦게 저장하지 못하도록 합니다.

강제 종료나 DB 장애로 남은 `queued`/`running`은 lease 만료 후 다음 조회에서 `SCAN_INTERRUPTED`가 됩니다. 다른 프로세스의 유효한 lease는 유지합니다. 검사 자동 재실행은 없으며 사용자가 새로 접수해야 합니다. 최종 저장도 유효한 lease와 미완료 상태를 다시 확인해 만료된 작업이 완료·실패 결과를 덮어쓰지 못하게 합니다.

| 응답·코드 | 의미·확인할 항목 |
|---|---|
| 503 `SCAN_SCHEMA_REQUIRED` | PostgreSQL 필수 테이블·컬럼 누락. 적용된 migration 확인 |
| 503 `SCAN_STORAGE_UNAVAILABLE` | DB 연결·접근 장애. 서버의 연결 설정과 DB 상태 확인 |
| 429 `SCAN_QUEUE_FULL` | API 프로세스의 접수 용량 초과. 응답의 재시도 안내 확인 |
| 결과의 `SCAN_INTERRUPTED` | 실행 주체가 작업을 완료하지 못하고 lease 만료 또는 종료 취소. 새 검사 필요 |
| 결과의 `ENGINE_FAILED` | 엔진 전체 실패. 응답의 도구별 coverage 확인 |

영속 저장은 중단된 검사 프로세스를 이어서 실행한다는 뜻이 아닙니다. DB 백업·보관 기간·삭제 정책은 이 저장 모듈에서 자동 관리하지 않습니다.

## 검증

저장소 루트에서 실행하는 Bash/Git Bash 예시입니다.

```bash
python -m pip install -r backend/requirements-dev.txt -r tests/security/requirements.txt
cd backend
ASYNC_JOB_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres \
  python -m pytest -q tests/test_scan_persistence.py tests/test_job_auth.py tests/test_explain_jobs.py
```

회귀 테스트는 내장 검사기 출력, 파일 SQLite, 임시 PostgreSQL DB로 저장·재조회·재검사 신뢰 경계·lease·소유권을 확인합니다. PostgreSQL 환경 변수가 없으면 해당 테스트는 건너뜁니다. 지정한 loopback 서버에 무작위 이름의 DB를 만들고 그 DB만 삭제하므로 일회용 개발 서버를 사용합니다. [CI](../.github/workflows/async-llm.yml)는 PostgreSQL 17에서 실행하며 실제 Supabase·GPU 통합 검증을 대신하지 않습니다.

구현 기준: [검사 API](../backend/app/routers/scans.py), [저장소](../backend/app/scan_store.py), [회귀 테스트](../backend/tests/test_scan_persistence.py).
