# LLM 작업 처리와 인증

LLM 작업은 두 가지 모드가 있습니다. 현재 웹·MCP의 서비스 흐름은 기본 미리보기 API를 사용하며, 사용자별 PostgreSQL 큐는 별도 연결이 필요한 선택 구성입니다. **둘 다 비동기지만 저장 수명과 인증·요청 규격이 다릅니다.**

## 기본 미리보기와 PostgreSQL worker

| 항목 | 기본 모드 (`LLM_JOBS_ENABLED=false`) | DB worker 모드 (`true`) |
|---|---|---|
| 접수 | `POST /api/llm/explain/tasks` | `POST /api/scans/{db_scan_id}/explanations` |
| 입력 | 최대 50개 `findings`와 `mode` | 저장된 scan ID, body `{}` |
| 조회 | `GET /api/llm/explain/tasks/{job_id}` | `GET /api/scans/{db_scan_id}/explanations` |
| 실행 | API 프로세스의 비동기 작업 | 별도 PostgreSQL worker |
| 보관 | 메모리, 재시작 시 유실 | DB의 작업·설명 결과 |
| 인증 | LLM 라우트 자체에 사용자 인증 없음 | 검증된 Supabase Bearer 및 소유권 검사 |
| 처리 단위 | 미리보기 입력 묶음 | DB finding 1개씩, `red_blue` |

기본 작업은 대기 시간을 포함해 900초 제한이며 완료 결과는 최대 50개·30분 동안 유지됩니다. 동시 실행과 접수 용량은 `LLM_PARALLEL_JOBS`, `LLM_MAX_CONCURRENCY`, `LLM_QUEUED_JOBS` 설정에 영향을 받습니다. 이는 아래 DB worker 설정과 별개입니다. [미리보기 구현](../backend/app/llm/preview_jobs.py)

`LLM_JOBS_ENABLED=true`이면 `/api/llm/explain`, `/api/llm/explain/tasks`, `/api/items`가 등록되지 않습니다. 현재 [웹 클라이언트](../frontend/src/lib/api.ts)와 [MCP 서비스](../integrations/mcp-handoff/service_api.py)의 미리보기 호출을 바꾸지 않고 플래그만 켜면 기능이 끊깁니다. `/api/llm/health`는 두 모드 모두 제공합니다.

`SCAN_REQUIRE_AUTH=true`만 설정하면 검사 접수·조회에 인증을 추가합니다. LLM 미리보기에는 인증이 추가되지 않으며 DB worker도 시작되지 않습니다. 두 플래그 모두 보고서·실행 검증 등 **전체 API에 인증을 거는 전역 스위치가 아닙니다.**

## DB worker의 요청 계약

다음 API의 ID는 검사 접수 `job_id`나 엔진 UUID가 아닌, PostgreSQL 검사 완료 응답의 **숫자 `db_scan_id`**입니다. Supabase 로그인에서 받은 access token을 사용합니다.

```javascript
const response = await fetch(`/api/scans/${dbScanId}/explanations`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({})
});
```

| 요청·상황 | 응답 |
|---|---|
| POST, body `{}` | 202 `{scan_id, queued_job_ids, poll_after_seconds: 2}`, `Location`에 조회 경로 |
| GET `?after_id=0&limit=50` | `{scan_id, items, next_after_id}`. 같은 사용자 인증 필요 |
| 인증 없음·위조·만료 | 401 |
| Supabase 익명 로그인 | 403 `LOGIN_REQUIRED` |
| Auth 서버 장애 | 503. 인증을 생략하는 fallback 없음 |
| 다른 소유자·익명 프로젝트·없는 scan | 동일하게 404 |
| 아직 검사 중인 scan | 409 `SCAN_NOT_READY` |
| 추가 body 필드·잘못된 ID·페이지 크기 | 422 |

한 POST는 `explain_status=none`인 finding을 최대 50개 접수합니다. 이미 접수·완료·실패한 항목을 중복 생성하지 않습니다. `explaining` scan의 나머지는 worker가 이어서 접수합니다. 과거 `done` scan은 `queued_job_ids=[]`까지 POST를 반복해야 전체를 접수할 수 있습니다. 실패한 finding의 재처리는 새 검사로 진행합니다.

조회 항목은 `finding_id`, `fingerprint`, `explain_status`, `job_id`, `job_status`, `attempts`, `result`, `error_code`입니다. 페이지 전체를 읽고 **다음 polling은 `after_id=0`부터** 시작해야 앞 페이지의 상태 변경을 볼 수 있습니다. `limit` 범위는 1–50이며 활성 작업이 있을 때 약 2초 간격으로 조회합니다.

- finding: `none → pending → done | failed | skipped`.
- job: `queued → running → done | failed | skipped`.
- 결과는 `ExplainResult` 구조입니다. provider의 원본 오류 문구는 DB 작업 결과에 저장·반환하지 않습니다.
- `failed`와 `skipped`를 성공 결과에서 숨기지 않습니다. Red pass는 LLM 검토 판정이며 실제 패치 적용·실행 검증 성공과 다릅니다.

## 인증과 저장 경계

백엔드는 서버에 설정된 HTTPS `SUPABASE_URL`의 `/auth/v1/user`를 호출하고 redirect를 따라가지 않습니다. 반환된 사용자 UUID를 검증한 뒤 `project.owner_id`와 비교합니다. 클라이언트가 보낸 user ID나 단순 decode한 토큰 payload를 신뢰하지 않습니다. DB에 직접 접근하는 백엔드는 RLS를 우회할 수 있어 이 소유권 검사가 필수입니다.

Supabase DB·Auth의 선행 조건과 migration 순서는 [데이터 저장 구조](db-erd.md#스키마-적용-순서)를 따릅니다. SQLite에서는 DB worker 활성화를 거부합니다. 로컬 고정 사용자나 인증 생략 모드는 없습니다. 현재 공개 웹·MCP에는 이 모드의 로그인·사용자 토큰·새 접수 API가 통합되어 있지 않습니다.

## worker 동작과 복구

[검사 저장 경로](scan-persistence.md)는 PostgreSQL에 모든 finding과 응답을 한 transaction으로 저장합니다. 소유자가 있고 finding이 있는 scan은 `explaining`으로 기록합니다. worker는 커밋된 이 scan을 찾아 작업을 자동 접수하므로 별도 POST가 없어도 처리가 시작됩니다. `SCAN_REQUIRE_AUTH=true`만 사용하고 worker를 실행하지 않으면 이 관계 테이블의 `explaining` 상태가 남을 수 있습니다.

worker는 `FOR UPDATE SKIP LOCKED`로 작업을 claim하고, GPU 호출 중에는 DB transaction을 열어 두지 않습니다. lease heartbeat와 claim마다 바뀌는 토큰으로 이전 worker의 뒤늦은 결과 저장을 막습니다. job·finding·explanation의 최종 저장은 한 transaction입니다.

| 설정 | 기본값 | 의미 |
|---|---|---|
| `LLM_JOB_LEASE_S` | 180초 | heartbeat는 이 값의 1/3 간격 |
| `LLM_JOB_TIMEOUT_S` | 900초 | 한 작업의 전체 실행 제한, 모델 HTTP timeout과 별개 |
| `LLM_JOB_POLL_S` | 2초 | 작업이 없을 때 조회 간격 |
| claim 재시도 | 최대 3회 | 프로세스 중단 등으로 lease를 잃은 작업. 소진 시 `WORKER_LOST` |

worker 한 프로세스는 finding 1개씩 항상 `red_blue`로 처리합니다. 모델의 실패 결과·입력 오류·전체 timeout은 terminal로 저장하며 무한 재시도하지 않습니다. 모든 finding이 terminal이면 `scan.status=done`으로 마감하지만 일부 설명은 실패했을 수 있습니다.

GPU 호출 자체는 exactly-once가 아닙니다. 응답 직후 프로세스가 죽으면 재호출될 수 있고, DB 저장만 토큰으로 보호합니다. 브라우저 종료가 DB 작업 취소를 의미하지 않으며 별도 취소 API는 없습니다. worker 수를 늘리면 LLM 동시성도 프로세스별로 늘어나므로 GPU 전체 용량을 별도로 관리해야 합니다.

## 활성화 절차

다음은 구현된 DB worker를 API로 직접 실행·검증하는 절차입니다. 현재 공개 웹·MCP를 이 모드로 전환하는 배포 절차는 아닙니다.

1. 대상 Supabase 프로젝트에 기본 스키마, `026-async-llm.sql`, `052-scan-persistence.sql`을 적용하고 DB와 Auth가 같은 프로젝트인지 확인합니다.
2. API와 worker가 같은 코드·DB·Auth·LLM 설정을 읽도록 구성합니다. 루트 `.env` 또는 서비스 환경 파일에 `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `LLM_JOBS_ENABLED=true`가 필요합니다. GPU 키는 서버에만 둡니다.
3. 내부 주소에서 API와 worker를 실행합니다. 아래는 의존성을 설치한 개발 환경의 Bash/Git Bash 예시이며 각각 별도 터미널에서 실행합니다.

   ```bash
   cd backend
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   ```bash
   cd backend
   python -m app.explain_jobs.worker
   ```

4. 실제 Supabase 사용자의 access token으로 검사를 접수·조회하고 완료 응답의 `db_scan_id`로 위 설명 API를 호출합니다. 두 사용자 간 소유권 격리, 무인증 401, 익명 로그인 403, 페이지 polling과 worker 복구를 확인합니다. 미리보기 및 Item 경로는 404여야 합니다.
5. 프록시를 통한다면 검사와 설명 API의 Bearer 헤더 전달을 확인합니다. 과거 [`Caddyfile.quick.example`](../deploy/llm-jobs/Caddyfile.quick.example)은 Basic 인증 데모용 예시이며 현재 공개 프록시 전체를 대체하는 설정이 아닙니다.

서버 상주 실행 예시는 [`72hours-llm-worker.service`](../deploy/llm-jobs/72hours-llm-worker.service)입니다. 파일의 경로·환경 파일은 실제 배포와 맞아야 합니다. 실행 중인 worker를 중지해도 DB의 큐·결과는 남습니다. API 플래그를 `false`로 되돌리면 인증 없는 미리보기 라우트가 다시 등록됩니다.

## 검증

저장소 루트에서 의존성을 설치하고 테스트를 실행합니다. Bash/Git Bash 예시입니다.

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
ASYNC_JOB_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres \
  python -m pytest -q tests/test_job_auth.py tests/test_explain_jobs.py
```

DB 환경 변수가 없으면 PostgreSQL 테스트는 건너뜁니다. 테스트는 loopback의 일회용 PostgreSQL에 새 DB를 생성·삭제하며 Auth와 LLM은 대역을 사용합니다. [CI](../.github/workflows/async-llm.yml)는 PostgreSQL 17에서 실행합니다. 이 결과가 실제 OAuth·프록시·GPU 연동 검증을 대신하지는 않습니다.

구현 기준: [라우팅](../backend/app/main.py), [인증](../backend/app/explain_jobs/auth.py), [API](../backend/app/explain_jobs/api.py), [큐 저장](../backend/app/explain_jobs/store.py), [worker](../backend/app/explain_jobs/worker.py).
