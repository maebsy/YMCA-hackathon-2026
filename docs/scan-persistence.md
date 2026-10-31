# 검사 결과 저장 (#52)

`POST /api/scans`는 DB에 작업을 접수한 뒤 202를 반환합니다. 검사 완료 시 전체 엔진 JSON과 API 응답을 `scan_job`에 저장하므로 API를 재시작해도 같은 `job_id`로 조회할 수 있습니다. 기존 메모리 전용 `_jobs`와 최근 50건 보관 제한을 제거했습니다.

## 적용

PostgreSQL에는 다음 SQL을 순서대로 적용합니다. 서버 시작 시 서비스 테이블을 자동 생성하지 않으며, 저장 스키마가 없으면 검사 요청은 503 `SCAN_SCHEMA_REQUIRED`를 반환합니다.

필수 테이블·컬럼 누락과 DB 연결 장애를 구분합니다. 연결 장애는 503 `SCAN_STORAGE_UNAVAILABLE`이고, 인증 모드에서는 DB 확인보다 Bearer 인증을 먼저 수행합니다.

1. [`db-schema.sql`](db-schema.sql)
2. 비동기 LLM을 사용할 경우 [`026-async-llm.sql`](migrations/026-async-llm.sql)
3. [`052-scan-persistence.sql`](migrations/052-scan-persistence.sql)

SQLite 로컬 데모에서는 `scan_job` 응답 테이블만 자동 생성합니다. 서비스 관계 테이블과 비동기 worker 연동은 PostgreSQL에서 검증합니다.

## 저장 계약

- PostgreSQL은 `project`, `scan`, 도구별 `tool_run`, **모든** `finding`, 응답 snapshot을 한 transaction으로 저장합니다. 중간 실패 시 전부 롤백하고 완료를 재호출해도 중복 삽입하지 않습니다.
- 일시적인 DB 연결·트랜잭션 오류는 계산된 결과를 유지한 채 1초·2초 후 저장만 재시도합니다(최대 3회). 검사 도구를 다시 실행하지 않습니다. 입력 검증·무결성 오류는 재시도하지 않으며, 커밋 응답만 유실된 경우도 이미 저장된 결과를 덮어쓰지 않습니다.
- API의 상위 50건 LLM 미리보기와 저장 개수는 별개입니다. 각 finding의 위치·패키지·전체 참조·마스킹된 원본을 보관합니다. 엔진 기본 출력에 `raw`가 없어도 정규화된 finding 전체가 `finding.raw`에 남습니다.
- 엔진 문자열 UUID `scan_id`는 그대로 유지합니다. 서비스 bigint ID는 완료 응답의 `db_scan_id`로 별도 반환합니다. `/api/scans/{job_id}` 조회에는 계속 접수 시의 UUID `job_id`를 사용합니다.
- LLM 제한을 넘는 긴 제목·경로·수정안도 원본을 저장합니다. 미리보기에서 제외한 항목은 `preview_errors`의 `LLM_INPUT_INVALID`로 표시하고, 비동기 worker 입력 오류는 해당 finding의 실패로 처리합니다.
- `LLM_JOBS_ENABLED=true`면 접수·조회 모두 검증된 Supabase Bearer 인증을 요구하고 소유자를 검사합니다. 소유자와 finding이 있는 scan은 저장 완료 시 `explaining`으로 전환되어 기존 worker가 처리합니다. 비로그인·발견 0건은 `done`, 엔진 전체 실패는 `failed`입니다.
- 기본 익명 모드는 기존의 추측 불가능한 job UUID로 조회합니다. UUID를 가진 사람은 결과를 읽을 수 있으므로 공유에 주의하며, authenticated 소유 결과를 익명 조회할 수는 없습니다. DB 직접 접근은 RLS와 역할별 권한 회수로 제한합니다.
- 재검사의 `previous`에는 기존 응답의 전체 `result` 또는 `{"scan_id":"이전 엔진 UUID"}`를 보낼 수 있습니다. 서버는 ID만 조회 키로 사용하고, 동일 저장소·소유자의 DB 저장본으로 비교합니다. 브라우저가 수정한 finding·코드·날짜는 사용하지 않습니다. 저장본이 없거나 다른 소유자·저장소이면 접수 전에 404 `PREVIOUS_SCAN_NOT_FOUND`를 반환합니다. DB에 저장되기 전 브라우저에만 남은 과거 결과도 새 검사부터 다시 시작해야 합니다. 익명 결과의 엔진 UUID도 재검사에 사용할 수 있는 접근 토큰으로 취급합니다.
- 실행 중에는 30초마다 120초 lease를 갱신합니다. 정상 종료 시 작업을 기다린 뒤 취소된 작업을 실패로 기록합니다. 동기 스캐너 thread 자체의 즉시 종료는 보장하지 않지만 취소된 작업은 결과를 뒤늦게 저장하지 않습니다. 강제 종료나 DB 장애로 남은 `queued`/`running`은 lease가 만료된 뒤 다음 조회에서 `SCAN_INTERRUPTED`가 됩니다. 검사 자동 재실행은 하지 않으며 사용자가 새로 접수할 수 있습니다. 다른 프로세스의 유효한 lease는 유지합니다.
- 최종 저장도 유효한 lease와 미완료 상태를 동시에 확인합니다. SQLite의 경쟁 저장이나 PostgreSQL의 잠금 대기 중 만료된 작업은 이미 완료·실패한 결과를 덮어쓸 수 없습니다. PostgreSQL lease는 transaction 시작 시각이 아닌 실제 DB 시각을 사용합니다.

## 재현·검증

수정 전 main `53ab830`에서는 실제 OSV 2.7.0·Opengrep 1.33.1·Gitleaks 8.30.1·config 0.1.0으로 생성한 합성 검사 결과 6건을 API에 연결해 접수 202 → 완료 조회 200을 확인했지만, SQL 저장은 0건이었습니다. #52의 원인은 JSON 생성 실패가 아니라 API의 저장 경로 부재였습니다.

회귀 테스트는 실제 내장 검사기 출력, 파일 SQLite, 새 임시 PostgreSQL DB를 사용합니다. PostgreSQL 테스트는 아래 환경 변수가 없으면 건너뜁니다. 지정한 서버에 임의 이름의 DB를 생성하고 그 DB만 삭제하므로 로컬 일회용 서버를 사용합니다.

```bash
pip install -r backend/requirements-dev.txt -r tests/security/requirements.txt
cd backend
ASYNC_JOB_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres \
  python -m pytest -q tests/test_scan_persistence.py tests/test_job_auth.py tests/test_explain_jobs.py
```

CI의 `async-llm.yml`도 PostgreSQL 17에서 저장 회귀 테스트를 실행합니다. 공용 Supabase나 실제 GPU를 변경하지 않으며, 운영 반영에는 위 SQL 적용과 인증·worker 설정이 필요합니다.
