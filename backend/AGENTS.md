# backend 작업 규칙

루트 [AGENTS.md](../AGENTS.md)를 먼저 읽습니다. 여기는 `backend/`에만 해당하는 내용입니다.

## 구조

| 경로 | 하는 일 | 담당 |
|---|---|---|
| `app/main.py` | 앱 진입점, 라우터 등록. 모든 API는 `/api` 아래 | 유영민·김건우 |
| `app/config.py`, `app/db.py`, `app/models.py` | `.env` 설정, DB 연결, 테이블 | 유영민·김건우 |
| `app/routers/scans.py`, `app/scan_store.py` | `POST /api/scans`, `GET /api/scans/{job_id}`, 검사 결과 저장 | 김건우·유영민 |
| `app/routers/llm.py`, `app/llm/` | `GET /api/llm/health`, `POST /api/llm/explain`, 해석 파이프라인 | 유영민 |
| `app/explain_jobs/` | 비동기 해석 큐와 worker (`llm_jobs_enabled`가 켜졌을 때만) | 유영민 |
| `app/routers/reports.py`, `app/reports/` | `POST /api/reports/plain`·`assess`·`incident-24h`·`privacy-72h` | 박기태 |
| `app/routers/items.py` | 연결 확인용 예시 | — |

설명 문서: [docs/llm.md](../docs/llm.md), [docs/async-llm.md](../docs/async-llm.md), [docs/reports.md](../docs/reports.md), [docs/scan-persistence.md](../docs/scan-persistence.md)

## 지킬 것

- **LLM 서버가 꺼져 있어도 API 서버는 떠야 합니다.** LLM 호출은 `app/llm/client.py`를 거칩니다. Red 검증을 끝까지 통과하지 못한 결과는 지금처럼 "수동 확인 필요"로 표시합니다.
- **위험도 판정은 코드가 합니다.** SSVC 결정은 `app/llm/risk.py`, OS별 명령은 `app/llm/remediation.py` 템플릿에서만 나옵니다. LLM이 명령이나 판정을 지어내게 바꾸지 않습니다.
- 요청·응답 형식은 `app/llm/schemas.py`, `app/reports/schemas.py`의 pydantic 모델로 정합니다. 필드 이름을 바꾸면 프론트(`frontend/src/types/security.ts`)와 MCP가 깨집니다. 루트 AGENTS.md 3장을 따릅니다.
- 새 라우터는 `app/routers/`에 새 파일로 만들고 `app/main.py`에는 등록 한 줄만 추가합니다.
- 의존성을 추가하면 `requirements.txt`(실행용) 또는 `requirements-dev.txt`(테스트용)와 `docs/external-resources.md`를 같은 PR에서 고칩니다.
- 비밀값·사용자 코드 원문을 로그에 남기지 않습니다.

## 실행과 테스트

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # macOS·Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000/api/health
python -m pytest -q
```

- 테스트는 가짜 vLLM 응답으로 돕니다. 실제 GPU 서버로 확인할 때만 `LLM_LIVE=1 pytest -m live -s`를 씁니다.
- PostgreSQL 저장 테스트는 `ASYNC_JOB_TEST_DATABASE_URL`에 지워도 되는 로컬 DB를 지정할 때만 돕니다. 공용 Supabase 주소를 넣지 않습니다.
- 실제 GPU 출력의 형식·한국어·속도 점검: `python -m app.llm.check` (결과는 커밋되지 않는 `outputs/`에 저장)
