# 보안엔진 검사 결과의 DB 저장 경로 조사 (#52)

2026-10-31, Windows x64 / Python 3.13에서 확인했습니다. 관련 이슈는 [#52](https://github.com/maebsy/YMCA-hackathon-2026/issues/52)입니다.

**결론:** 엔진의 JSON 생성은 동작합니다. 현재 검사 API는 결과를 프로세스 메모리에 보관하며, 서비스 DB의 `scan`·`tool_run`·`finding`으로 저장하지 않습니다. 이 문서는 조사 결과를 기록하며 #52의 DB 저장 기능 구현은 별도 작업으로 남깁니다.

## main 변경에 따른 관찰 구분

| 검증 기준 | 관찰 |
|---|---|
| `f6a5a1bbc081d734fb379e24bbde478e1d4b8c0a` | `POST /api/scans`가 없어 404. 올바르게 변환한 엔진 입력으로 해석 API가 200을 반환해도 SQL 실행은 0건 |
| `53ab8307595ffa8fe160dbc73c5bb229e8afea2a` (#51 머지 후) | 검사 API가 추가됨. 접수 202 → 조회 200 / done까지 동작하나 결과는 `_jobs` 메모리에만 보관. 실제 엔진 결과 6건을 연결한 접수·조회 probe의 SQL 실행은 0건 |

따라서 이전 조사에서 관찰한 검사 API의 404는 첫 번째 커밋에 한정됩니다. #51은 검사 실행·화면 연결을 추가했으며, DB 저장 부재라는 #52의 범위는 남아 있습니다.

## 실제 설치·검사 결과

저장소의 [설치 스크립트](../../scripts/security/install-test-tools.py)로 공식 SHA-256을 검증했습니다. 전역 PATH를 바꾸지 않고 아래 버전을 설치했습니다.

| 도구 | 버전 | 합성 취약 사이트의 실행 상태 |
|---|---|---|
| OSV-Scanner | 2.7.0 | ok, 0건 |
| Opengrep | 1.33.1 | ok, 코드 문제 5건 |
| Gitleaks | 8.30.1 | ok, 합성 비밀값 1건 |
| 내장 config | 0.1.0 | ok, 0건 |

`tests/security/conftest.py`의 취약 사이트 fixture를 저장소 밖 임시 폴더에 만들고 CLI `scan`·`llm-input`을 실행했습니다. 결과는 `status=complete`, findings 6건, LLM 입력 items 6건이며 [검사 JSON 스키마](../../security_engine/schema/scan_result.schema.json)를 통과했습니다. 합성 비밀값의 원문은 두 JSON에 남지 않았습니다. OSV의 0건은 이 fixture의 관찰값이며 일반적인 탐지율을 뜻하지 않습니다.

최초 fixture를 `outputs/` 아래에 두었을 때는 상위 `.gitignore`의 영향으로 검사 범위가 달라졌습니다. 해당 결과는 버리고 저장소 밖에서 다시 검사한 결과만 위에 기록했습니다.

## API·저장 경계 확인

`.env`가 없는 조사 worktree에서 process-local in-memory SQLite와 fake LLM을 사용했습니다. 공용 DB·GPU에는 연결하지 않았습니다.

첫 번째 커밋에서 실제 생성 JSON으로 다음을 확인했습니다.

| 입력 | `/api/llm/explain` 관찰 |
|---|---|
| 원본 `scan.json` | 422. 이 fixture의 문자열 `flags`와 API의 객체형 `FindingFlag`가 불일치 |
| 원본 `llm-input.json` | 422. API가 요구하는 `findings` wrapper 없음 |
| `from_engine_payload(llm_input)` → `{"findings": [...]}` | 200, fake 해석 결과 6건, 요청 중 SQL 실행 0건 |

`from_engine_payload(scan_result)`는 `items` 키가 없어 빈 목록을 반환했습니다. 이 adapter는 `llm-input` 변환용입니다. 원본 scan 결과를 받는 저장 API로 해석하면 안 됩니다.

두 번째 커밋에서는 `scan_repo`의 clone 경계만 앞서 생성한 실제 엔진 결과로 대체하고 기존 background worker를 실행했습니다.

- `POST /api/scans`는 202, 완료된 작업의 `GET /api/scans/{job_id}`는 200 / done.
- 응답의 원본 findings와 변환된 API findings가 모두 6건.
- 접수·조회 중 SQL 실행 0건. 기본 모드 startup이 생성한 테이블은 데모용 `item`뿐.
- `_jobs`를 명시적으로 비운 뒤 동일한 job 조회는 404. 이는 메모리 소거 probe이며 실제 서버 재시작 실험은 아닙니다.

## 근거와 남은 연결 계약

- [검사 router](../../backend/app/routers/scans.py)는 결과의 메모리 보관을 명시하고, `OrderedDict`인 `_jobs`에 작업과 결과를 저장합니다. 최대 50건 보관이며 DB 저장은 추후 개발 대상으로 적혀 있습니다.
- [해석 API](../../backend/app/routers/llm.py)는 explainer의 응답을 반환합니다. 성공 응답이 영속화를 의미하지 않습니다.
- [엔진 adapter](../../backend/app/llm/engine_adapter.py)는 LLM 입력 변환을 담당합니다.
- [비동기 store](../../backend/app/explain_jobs/store.py)는 이미 저장된 scan/finding으로 작업을 만들고 설명 결과를 저장합니다. scanner finding을 생성하는 단계는 아닙니다.
- [DB 매핑](../db-erd.md#엔진--db--llm-계약)과 [비동기 연동 문서](../async-llm.md)는 모든 finding 및 adapter 규격의 `llm_context` 저장과 `scan.status='explaining'` 전환을 한 transaction으로 커밋하도록 정의합니다.

연동 시 엔진 문자열 `scan_id`와 DB bigint identity의 대응, location/package/references의 컬럼 변환, 기본 출력에 생략되는 `raw`의 마스킹·보관 정책이 필요합니다. 이는 계약에서 확인한 변환 요건이며 실제 UUID→bigint 저장 오류를 관찰했다는 의미는 아닙니다. 저장·rollback·소유권·재시도·발견 0건·worker 인계 검증은 #52의 완료 조건입니다.

## 재현 절차

아래 명령은 `.env`가 없는 별도 worktree의 루트에서 실행합니다. 운영 설정이나 공용 DB 주소를 복사하지 않습니다.

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r tests/security/requirements.txt -r backend/requirements-dev.txt
.venv/Scripts/python.exe scripts/security/install-test-tools.py --destination outputs/scanners
$env:SECURITY_ENGINE_OSV_BIN=(Resolve-Path outputs/scanners/osv-scanner_windows_amd64.exe).Path
$env:SECURITY_ENGINE_SEMGREP_BIN=(Resolve-Path outputs/scanners/opengrep_windows_x86.exe).Path
$env:SECURITY_ENGINE_GITLEAKS_BIN=(Resolve-Path outputs/scanners/gitleaks.exe).Path
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe -m security_engine doctor
.venv/Scripts/python.exe -m pytest tests/security -q
```

검사 API의 저장 경계는 외부 clone 없이 아래 probe로도 재현할 수 있습니다. 합성 임시 파일을 내장 config 검사기로 검사하고 실제 background worker의 결과 보관을 확인합니다. 루트에서 Python에 전달합니다.

```powershell
@'
import asyncio, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
root = Path.cwd()
assert not (root / '.env').exists()
os.environ.update(DATABASE_URL='sqlite://', LLM_JOBS_ENABLED='false',
    LLM_BASE_URL='http://127.0.0.1:9/v1', LLM_API_KEY='probe-only',
    LLM_THREAT_INTEL='false', LLM_ANALYZE_CONTEXT='false')
sys.path.insert(0, str(root / 'backend'))
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
import app.db as db
db.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
from app.main import app
from app.routers import scans
from fastapi.testclient import TestClient
import security_engine
from security_engine import ScanOptions, scan
sql = []
event.listen(db.engine, 'before_cursor_execute', lambda c, cur, stmt, p, ctx, many: sql.append(stmt))
with tempfile.TemporaryDirectory() as folder:
    target = Path(folder)
    (target / '.env').write_text('SYNTHETIC_NAME=placeholder\n', encoding='utf-8')
    def local_scan(repo_url, previous=None):
        return scan(target, previous, options=ScanOptions(tools=('config',)), repo_url=repo_url)
    with patch.object(security_engine, 'scan_repo', local_scan), TestClient(app) as client:
        sql.clear()  # startup DDL은 측정에서 제외
        start = client.post('/api/scans', json={'repo_url': 'https://github.com/example/fixture'})
        assert start.status_code == 202
        job_id = start.json()['job_id']
        async def wait_job():
            for _ in range(100):
                if scans._jobs[job_id]['status'] in ('done', 'failed'):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError('worker timeout')
        client.portal.call(wait_job)
        job = client.get(f'/api/scans/{job_id}').json()
        assert job['status'] == 'done' and job['result']['findings']
        assert sql == [], sql
        client.portal.call(scans._jobs.clear)
        assert client.get(f'/api/scans/{job_id}').status_code == 404
        print('202 -> done; SQL=0; explicit memory clear -> 404')
'@ | .venv/Scripts/python.exe -
```

## 검증과 한계

- 엔진 회귀 테스트: **29 passed / 0 skipped**.
- 최신 기준의 engine adapter·dependency grouping·LLM API·scan API 테스트: **32 passed / 0 skipped**. fake 응답과 process-local in-memory SQLite로 실행했습니다. anyio assertion rewrite 및 Starlette/httpx deprecation 경고 2건이 있었습니다.
- 최초 제보자의 실제 실행 브랜치·JSON·오류 로그, 공용 Supabase 적용 상태, 실제 GPU 호출과 PostgreSQL 저장 E2E는 확인하지 않았습니다.
- 전체 scanner JSON·고객 데이터·자격 증명·개인별 절대 경로는 이 문서에 포함하지 않습니다.
