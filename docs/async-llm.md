# #26 비동기 LLM 처리와 인증

기존 API가 LLM 완료까지 연결을 유지하던 문제를 DB 큐와 별도 worker로 분리합니다. 사용자는 자신의 **저장된 scan ID**로 요청하고 202를 받은 뒤 상태를 조회합니다. 임의 finding/prompt/모델/GPU 주소는 요청으로 받지 않습니다.

기능은 기본 **비활성**입니다. 이번 PR은 실행 중인 서비스·GPU·공용 DB·프론트를 배포하거나 수정하지 않습니다. Claude의 #29가 수정하는 `app/llm/*`도 바꾸지 않습니다. 기존 `Explainer.explain_many`를 호출합니다.

## 선행 조건과 DB 소유 범위

- #7의 `docs/7-db-design` 초안을 기준으로 구현했습니다. 기준 SQL blob: `4e04ffaecb5c34306b886603e41855c049fc1345`.
- 원본 설계 브랜치는 수정하지 않았습니다. 리뷰용 추가 SQL은 [`migrations/026-async-llm.sql`](migrations/026-async-llm.sql)입니다.
- #7 담당자가 테이블/필드를 확정하고 **#7 → #26 순서로 SQL을 적용**해야 활성화할 수 있습니다. API 시작 시 DDL·migration·`create_all`을 실행하지 않습니다.
- 추가 항목: `finding.explain_status=skipped`, 스캐너 전용 `finding.llm_context`, explanation의 D/Red 검증 필드, RLS를 켠 `llm_job` 큐. 기존 B/C 기록은 유지하고 과거 설명의 `needs_manual_review` 기본값은 true로 둡니다.
- PostgreSQL만 지원합니다. SQLite에서 활성화하면 시작을 거부합니다. 로컬 고정 사용자·검증 생략 모드는 없습니다.
- `backend/tests/fixtures/db_schema_7.sql`은 위 #7 초안의 **테스트 스냅샷**입니다. 운영 migration의 대체 파일이 아닙니다. 최종 #7 변경 시 fixture와 adapter를 함께 재검증해야 합니다.

## 프론트 계약

Supabase 로그인에서 받은 **access token**을 다음과 같이 전송합니다. 시연용 Basic 비밀번호, Supabase service-role 키 또는 GPU 키를 전송하지 않습니다.

```javascript
const response = await fetch(`/api/scans/${scanId}/explanations`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({})
});
// 202면 GET으로 진행 상태 조회. HTTP timeout/새로고침이 GPU 취소를 뜻하지는 않음.
```

| 요청 | 결과 |
|---|---|
| `POST /api/scans/{id}/explanations`, body `{}` | 202 `{scan_id, queued_job_ids, poll_after_seconds:2}`, Location에 조회 경로 |
| `GET /api/scans/{id}/explanations?after_id=0&limit=50` | `{scan_id, items, next_after_id}`. 같은 Bearer 토큰 필요 |
| 인증 없음/위조/만료 | 401, Supabase Auth 장애는 503으로 실패 처리 |
| 다른 사용자·비로그인 프로젝트·없는 scan | 동일하게 404 |
| 아직 scanning 등 검사 진행 중인 scan에 enqueue | 409 `SCAN_NOT_READY` |
| 임의 findings/mode 등 추가 body 필드, 잘못된 ID/페이지 크기 | 422 |

한 번에 최대 50개의 `none` finding을 큐에 넣습니다. 반복 POST는 이미 pending/완료/실패한 항목을 재생성하지 않습니다. `explaining` scan의 나머지 항목은 worker가 자동으로 이어서 큐에 넣습니다. 과거 `done` scan을 채우려면 POST를 반복해 `queued_job_ids=[]`가 될 때까지 요청합니다. 기존 실패 작업은 자동으로 재생성하지 않으며 새 검사로 다시 진행합니다.

조회 항목은 `finding_id`, `fingerprint`, `explain_status`, `job_id`, `job_status`, `attempts`, `result`, `error_code`입니다. `job_id/result`는 아직 작업이 없으면 null입니다. 페이지 전체를 읽은 뒤 다음 polling 때는 `after_id=0`부터 다시 조회해야 앞 페이지의 상태 변경을 놓치지 않습니다. 활성 작업이 있을 때만 약 2초 간격으로 조회합니다.

- finding 상태: `none → pending → done | failed | skipped`.
- job 상태: `queued → running → done | failed | skipped`.
- 완료 결과는 기존 `ExplainResult` 구조입니다. 원본 provider `error`는 저장/반환하지 않습니다.
- `failed`/`skipped`도 결과입니다. 일부 성공만 있어도 나머지를 숨기지 않습니다.
- Red pass는 LLM 검토 결과입니다. 코드 수정/취약점 해결 완료와 다릅니다. MCP 전달은 #23의 별도 pass/수동확인/오탐/대상 커밋 검증 규칙을 유지합니다.
- #29의 패키지 묶기 계약은 이 PR에서 변경하지 않습니다. 현재 큐 단위는 **DB finding 1개**입니다. #29 통합 시 묶음 대표 finding과 covers를 DB에 저장하는 계약을 별도로 맞춰야 합니다.

## 인증과 접근 제어

백엔드는 [Supabase 사용자 조회](https://supabase.com/docs/reference/python/auth-getuser)에 해당하는 `GET {SUPABASE_URL}/auth/v1/user`를 호출합니다. HTTPS와 서버 설정의 고정 URL만 사용하고 redirect를 따라가지 않습니다. 토큰 payload를 단순 decode해서 신뢰하거나, 브라우저가 보낸 user ID를 신뢰하지 않습니다. 응답의 검증된 사용자 UUID로 `project.owner_id`를 조회하고 scan 하위 데이터를 제한합니다. Supabase 익명 로그인은 LLM 요청에 허용하지 않습니다.

#7은 DB 직접 접속 사용자가 RLS를 우회하므로 **API 소유권 검사가 필수**라는 설계입니다. 데이터는 FastAPI를 통해서만 읽습니다. claim token으로 익명 프로젝트를 가져오는 기능, OAuth 화면, 프로젝트 생성은 이번 범위에 없습니다. 인증 서버 장애 시 허용하는 fallback도 없습니다.

## 스캐너·worker 계약

스캐너/오케스트레이터는 다음 작업을 하나의 DB transaction으로 커밋합니다.

1. 로그인 사용자의 project에 scan/finding을 저장합니다. `raw`·snippet의 비밀값은 저장 전에 마스킹합니다.
2. 정규 컬럼 밖의 LLM 입력은 `finding.llm_context` JSON 객체에 넣습니다: `status`, `change`, `flags`, `fix_hint`, `what`, `context` 등. DB 컬럼에 있는 fingerprint·파일 위치·패키지 정보는 context가 덮어쓸 수 없습니다.
3. 해당 scan의 결과 저장이 모두 끝나면 `scan.status='explaining'`으로 바꿉니다. 그 이후 finding 입력은 불변으로 취급하고 재검사는 새 scan을 만듭니다.

worker가 커밋된 `explaining` scan 중 owner가 있는 항목을 자동 발견해 큐에 넣습니다. HTTP 요청이 없어도 처리됩니다. **현재 main에는 스캐너 저장 API가 없으므로 #15/#7 오케스트레이터가 이 계약을 연결해야 합니다.** 빈 scan은 엔진이 직접 done으로 마감합니다. 모든 finding이 terminal이면 worker는 explaining scan을 done으로 마감하며, 개별 failed가 없다는 의미로 사용해서는 안 됩니다.

작업은 PostgreSQL의 [FOR UPDATE SKIP LOCKED](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.GenerativeSelect.with_for_update)로 claim합니다. CPU/GPU를 사용하는 동안 DB transaction을 열어 두지 않습니다. lease heartbeat와 매 claim의 새 토큰을 사용해 만료된 worker가 새 결과를 덮어쓰지 못하게 합니다. job/result/explanation/finding 상태 저장은 하나의 transaction입니다.

- 기본 worker 1개, 한 번에 finding 1개, 항상 `red_blue`. API 프로세스는 LLM 생성을 하지 않습니다.
- 기본 lease 180초, heartbeat 60초, 전체 작업 제한 900초. 모델 호출의 기존 timeout과 별개입니다.
- 프로세스 강제 종료/DB 장애로 유실된 lease는 재시작 후 다시 claim하며 최대 3번까지입니다. 소진되면 `WORKER_LOST` 실패로 표시합니다.
- 모델의 failed 결과/입력 오류/전체 timeout은 terminal로 저장합니다. 무한 재시도하지 않습니다.
- GPU 호출 자체는 exactly-once가 아닙니다. 프로세스가 응답 직후 죽거나 lease가 만료되면 재호출될 수 있습니다. DB 결과 저장만 토큰으로 보호합니다.
- 브라우저 취소는 DB 작업을 취소하지 않습니다. GPU 요청 취소를 보장하는 별도 API도 아직 없습니다.
- 워커 수를 늘리면 기존 LLM 동시성 한도는 프로세스별로 늘어납니다. GPU 용량 검증 없이 증설하지 않습니다.

## 활성화 절차 (이번 작업에서는 실행하지 않음)

1. #7 DB 담당자가 추가 SQL과 스캐너 저장 계약을 리뷰합니다. 테스트 DB에서 #7/#26 순서로 적용하고 백업·운영 반영 시점을 정합니다.
2. Supabase Auth의 OAuth 설정/프론트 로그인을 완료하고 팀 공용 DB·프로젝트의 주소를 서버 전용 환경 파일에 설정합니다.
3. 새로운 backend release에 `LLM_JOBS_ENABLED=true`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`을 설정합니다. GPU 키는 기존 서버 전용 설정을 유지합니다.
4. API를 먼저 내부 주소에서 기동해 무인증 401, 다른 소유자 404, `/api/llm/explain`과 `/api/items` 404를 확인합니다. true 모드에서는 이 평가/예제 경로를 등록하지 않습니다.
5. [`deploy/llm-jobs/Caddyfile.quick.example`](../deploy/llm-jobs/Caddyfile.quick.example)을 #25 구성과 검토합니다. **정확한 새 작업 API 경로만** Bearer 인증을 위해 Basic 영역에서 분리하고 웹/나머지는 기존 Basic을 유지합니다. 이 경로는 FastAPI에서 반드시 인증돼야 합니다. 단순히 Basic을 전체 해제하지 않습니다.
6. 실제 설정으로 Caddy validate 후 인증 프록시만 조율해 재시작합니다. cloudflared/GPU 재시작은 필요하지 않습니다. API가 준비되기 전에 프록시를 바꾸지 않습니다.
7. [`72hours-llm-worker.service`](../deploy/llm-jobs/72hours-llm-worker.service)를 사용자 systemd에 설치하고 daemon-reload 후 enable/start합니다. 자동 설치/시작 스크립트는 제공하지 않습니다.
8. 로그인된 테스트 사용자 2명으로 소유권 격리, 1건 처리, polling, worker 중단/재시작을 확인한 뒤 프론트에 사용 가능 상태를 전달합니다.

끄려면 worker를 먼저 중지하고 API/프록시를 함께 이전 release로 복구합니다. 큐 테이블과 결과는 삭제하지 않습니다. `LLM_JOBS_ENABLED=false`만 바꾸면 평가 API가 다시 활성화되므로 외부 보호 경계를 먼저 확인해야 합니다. DB migration 역적용은 기록 손실이 생길 수 있어 자동화하지 않습니다.

## 검증

```bash
cd backend
python -m pytest -q
# 본인 PC의 일회용 PostgreSQL만 지정. 테스트가 임의 이름의 새 DB를 만들고 그 DB만 삭제합니다.
ASYNC_JOB_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres \
  python -m pytest -q tests/test_job_auth.py tests/test_explain_jobs.py
```

`async-llm.yml`은 CI의 일회용 PostgreSQL 17에서 같은 테스트를 실행합니다. Windows 독립 PostgreSQL 17.11에서도 인증·큐 통합 테스트 36개를 확인했습니다. Auth는 MockTransport, LLM은 fake를 사용하여 실제 Supabase·GPU·공용 DB를 호출하지 않습니다. 실제 OAuth 로그인·시연 프록시 전환·GPU 생성은 운영 통합 단계의 검증 항목입니다.
